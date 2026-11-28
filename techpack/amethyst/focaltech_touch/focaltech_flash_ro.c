// SPDX-License-Identifier: GPL-2.0-only
/*
 * Read-only replacement for the FocalTech firmware-upgrade module on amethyst.
 *
 * The donor (MiCode popsicle-w-oss, q200/focaltech_3383) ships
 * focaltech_flash.c and an IC-specific upgrade file that erase and rewrite
 * the controller flash at probe time and from sysfs/procfs. Flash writing is
 * disabled on this port, so those files are not built. This file provides
 * the part of their API the rest of the driver uses:
 *
 *   - fts_flash_read(), fts_read_lockdown_info*(): read-only access to the
 *     controller flash in bootloader mode, used for the 8-byte lockdown
 *     (panel/vendor) record. The command sequence is the read subset of the
 *     donor's: reset-to-boot via register 0xFC, read boot ID (0x55/0x90),
 *     set read address (0xAC), read (0x03), reset (0x07). No erase (0x61),
 *     flash-mode (0x09), write (0xBF/0xAE) or ECC command is ever sent.
 *   - fts_fwupg_init()/fts_fwupg_exit(): no upgrade; they only run the
 *     post-upgrade initialisation the donor did at the end of its upgrade
 *     work (xiaomi_touch registration and enabling THP frame output).
 *   - fts_upgrade_bin(), fts_enter_test_environment(): refuse with an error.
 *   - fts_user_write_allowed(): filter for userspace-originated raw bus
 *     writes so that they cannot put the controller into its bootloader.
 *
 * FT3683G parameters (lockdown address, boot ID, register 0xFC, upgrade
 * spec 1.0, no pramboot) were taken from the stock module's data tables;
 * see docs/amethyst-drivers/focaltech.md.
 */

#include "focaltech_core.h"
#include "focaltech_flash.h"

#define FTS_RO_LOCKDOWN_ADDR		0x3F000
#define FTS_RO_LOCKDOWN_LEN		0x20

static bool fts_ro_in_bootloader(struct fts_ts_data *ts_data)
{
	struct ft_chip_t *ids = &ts_data->ic_info.ids;
	u8 cmd = FTS_CMD_START1;
	u8 val[2] = { 0 };
	int i;

	for (i = 0; i < FTS_UPGRADE_LOOP; i++) {
		/* Upgrade spec 1.0: one-byte start command, one-byte read ID */
		cmd = FTS_CMD_START1;
		if (fts_write(&cmd, 1) >= 0) {
			msleep(FTS_CMD_START_DELAY);
			cmd = FTS_CMD_READ_ID;
			if (fts_read(&cmd, FTS_CMD_READ_ID_LEN_INCELL, val, 2) >= 0 &&
			    val[0] == ids->bl_idh && val[1] == ids->bl_idl) {
				FTS_INFO("in bootloader, boot id:0x%02x%02x",
					 val[0], val[1]);
				return true;
			}
		}
		msleep(FTS_DELAY_READ_ID);
	}

	FTS_ERROR("not in bootloader, last boot id:0x%02x%02x", val[0], val[1]);
	return false;
}

static int fts_ro_reset_in_boot(void)
{
	u8 cmd = FTS_CMD_RESET;
	int ret;

	ret = fts_write(&cmd, 1);
	if (ret < 0)
		FTS_ERROR("bootloader reset cmd write fail, ret=%d", ret);
	msleep(FTS_DELAY_UPGRADE_RESET);
	return ret;
}

static int fts_ro_enter_bootloader(struct fts_ts_data *ts_data)
{
	int ret;

	if (fts_wait_tp_to_valid() == 0) {
		ret = fts_write_reg(FTS_REG_UPGRADE, FTS_UPGRADE_AA);
		if (ret < 0)
			return ret;
		msleep(FTS_DELAY_UPGRADE_AA);
		ret = fts_write_reg(FTS_REG_UPGRADE, FTS_UPGRADE_55);
		if (ret < 0)
			return ret;
		msleep(FTS_DELAY_UPGRADE_RESET);
	}

	return fts_ro_in_bootloader(ts_data) ? 0 : -EIO;
}

static int fts_ro_flash_read_buf(u32 saddr, u8 *buf, u32 len)
{
	u8 wbuf[FTS_LEN_SET_ADDR];
	u32 off, plen, addr;
	int ret;

	for (off = 0; off < len; off += plen) {
		plen = min_t(u32, len - off, FTS_FLASH_PACKET_LENGTH);
		addr = saddr + off;

		wbuf[0] = FTS_CMD_SET_RFLASH_ADDR;
		wbuf[1] = BYTE_OFF_16(addr);
		wbuf[2] = BYTE_OFF_8(addr);
		wbuf[3] = BYTE_OFF_0(addr);
		ret = fts_write(wbuf, FTS_LEN_SET_ADDR);
		if (ret < 0) {
			FTS_ERROR("set flash read address fail, ret=%d", ret);
			return ret;
		}

		msleep(FTS_CMD_READ_DELAY);
		wbuf[0] = FTS_CMD_READ;
		ret = fts_read(wbuf, 1, buf + off, plen);
		if (ret < 0) {
			FTS_ERROR("flash read cmd fail, ret=%d", ret);
			return ret;
		}
	}

	return 0;
}

int fts_flash_read(u32 addr, u8 *buf, u32 len)
{
	struct fts_ts_data *ts_data = fts_data;
	int ret, rst;

	if (!ts_data || !buf || !len)
		return -EINVAL;
	if (ts_data->bus_type != BUS_TYPE_SPI_V2) {
		FTS_ERROR("flash read only implemented for SPI_V2 bus");
		return -EOPNOTSUPP;
	}

	FTS_INFO("read flash 0x%x, len %u (read-only)", addr, len);
	if (ts_data->irq)
		fts_irq_disable();

	ret = fts_ro_enter_bootloader(ts_data);
	if (ret < 0)
		FTS_ERROR("enter bootloader fail, ret=%d", ret);
	else
		ret = fts_ro_flash_read_buf(addr, buf, len);

	/* Always leave the bootloader so that the application restarts. */
	rst = fts_ro_reset_in_boot();
	if (!ret && rst < 0)
		ret = rst;

	if (ts_data->irq)
		fts_irq_enable();
	return ret;
}

/* Raw lockdown bytes, FTS_LOCKDOWN_INFO_SIZE of them, into buf. */
int fts_read_lockdown_info_proc(u8 *buf)
{
	u8 info[FTS_RO_LOCKDOWN_LEN] = { 0 };
	int ret;

	ret = fts_flash_read(FTS_RO_LOCKDOWN_ADDR, info, sizeof(info));
	if (ret < 0) {
		FTS_ERROR("read lockdown info fail, ret=%d", ret);
		return ret;
	}

	memcpy(buf, info, FTS_LOCKDOWN_INFO_SIZE);
	FTS_INFO("lockdown info: %*ph", FTS_LOCKDOWN_INFO_SIZE, buf);
	return 0;
}

/* Lockdown bytes as text (" %02x " each), for the sysfs/debug readers. */
int fts_read_lockdown_info(u8 *buf)
{
	u8 info[FTS_LOCKDOWN_INFO_SIZE];
	int ret, i, count = 0;

	ret = fts_read_lockdown_info_proc(info);
	if (ret < 0)
		return ret;

	for (i = 0; i < FTS_LOCKDOWN_INFO_SIZE; i++)
		count += sprintf(buf + count, " %02x ", info[i]);
	return 0;
}

static void fts_fwupg_work(struct work_struct *work)
{
	/*
	 * The donor ran this after its (here removed) upgrade: register with
	 * xiaomi_touch once lockdown/firmware version are readable, then
	 * enable THP frame reporting.
	 */
	fts_init_xiaomi_touchfeature_v3(fts_data);
	fts_enable_touch_raw(1);
}

int fts_fwupg_init(struct fts_ts_data *ts_data)
{
	if (!ts_data || !ts_data->ts_workqueue) {
		FTS_ERROR("ts_data/workqueue is NULL");
		return -EINVAL;
	}

	FTS_INFO("firmware upgrade disabled on this build; using the firmware already in the controller flash");

	if (fts_get_lockdown_information(ts_data))
		FTS_ERROR("get lockdown information fails");

	INIT_WORK(&ts_data->fwupg_work, fts_fwupg_work);
	queue_work(ts_data->ts_workqueue, &ts_data->fwupg_work);
	return 0;
}

int fts_fwupg_exit(struct fts_ts_data *ts_data)
{
	cancel_work_sync(&ts_data->fwupg_work);
	return 0;
}

int fts_upgrade_bin(char *fw_name, bool force)
{
	FTS_ERROR("firmware upgrade (%s, force=%d) refused: flash writing is disabled",
		  fw_name ? fw_name : "(null)", force);
	return -EPERM;
}

int fts_enter_test_environment(bool test_state)
{
	/* The donor's version was an empty stub; the factory test is not built. */
	FTS_ERROR("test environment switch (%d) not supported", test_state);
	return -EOPNOTSUPP;
}

/*
 * Userspace may send raw bus writes through the APK debug proc node, the
 * fts_wr_reg/fts_htc_cmd sysfs nodes and the THP HAL's IC_MODE_44 path. Any
 * flash operation first requires the bootloader, which is entered either by
 * writing 0xAA/0x55 to register 0xFC (or 0xBC) or by the 0x55/0xAA start
 * command after reset. Reject those so no userspace path can reach flash.
 */
bool fts_user_write_allowed(const u8 *buf, u32 len)
{
	if (!buf || !len)
		return false;

	switch (buf[0]) {
	case FTS_REG_UPGRADE:
	case FTS_REG_UPGRADE2:
	case FTS_CMD_START1:
	case FTS_CMD_START2:
		FTS_ERROR("raw write starting 0x%02x refused (bootloader entry)", buf[0]);
		return false;
	default:
		return true;
	}
}
