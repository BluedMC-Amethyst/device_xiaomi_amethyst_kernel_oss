/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * Xiaomi/QTI compatibility hooks for the ST21NFC driver (Redmi Note 14 Pro+
 * "amethyst", SM7635).
 *
 * The stock vendor_dlkm stm_nfc_i2c.ko is built from the QTI
 * vendor/st/opensource/driver tree (ST 2.2.0.19 plus QTI changes).  Only the
 * pieces of that tree that are active in the stock binary are reproduced
 * here; see docs/amethyst-drivers/nfc.md for the differential analysis.
 */
#ifndef __ST21NFC_XIAOMI_H
#define __ST21NFC_XIAOMI_H

#include <linux/device.h>

/*
 * QTI "secure zone" (dynamic NFC peripheral protection) ioctl.  The stock
 * driver is built without NFC_SECURE_PERIPHERAL_ENABLED, so it rejects this
 * command with -EINVAL; we do the same rather than pretend to support it.
 */
#define NFC_SECURE_ZONE _IO(ST21NFC_MAGIC, 0x0B)

#ifdef ST21NFC_XIAOMI_COMPAT
int st21nfc_xm_clkreq_wake_setup(struct device *dev);
#else
static inline int st21nfc_xm_clkreq_wake_setup(struct device *dev)
{
	return 0;
}
#endif

#endif /* __ST21NFC_XIAOMI_H */
