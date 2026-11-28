// SPDX-License-Identifier: GPL-2.0-only
/*
 * Xiaomi/QTI compatibility hooks for the ST21NFC driver (amethyst).
 *
 * Behaviour follows the QTI vendor/st/opensource/driver st21nfc.c
 * (Copyright (c) 2022-2023 Qualcomm Innovation Center, Inc.), as used by the
 * stock Xiaomi stm_nfc_i2c.ko.  See ORIGIN for the donor reference.
 */

#include <linux/kernel.h>
#include <linux/of.h>
#include <linux/pinctrl/qcom-pinctrl.h>

#include "st21nfc.h"
#include "st21nfc_xiaomi.h"

/*
 * Make the NFCC CLK_REQ line a wake-capable interrupt in the MSM power
 * manager (MPM), so that the NFC controller can request the reference clock
 * while the SoC is in deep sleep (card emulation with the screen off).
 *
 * The TLMM GPIO number is the first cell after the phandle of the
 * "clkreq-gpios" property, e.g. <&tlmm 6 0> on amethyst.
 */
int st21nfc_xm_clkreq_wake_setup(struct device *dev)
{
	u32 clkreq_gpio = 0;
	int ret;

	ret = of_property_read_u32_index(dev->of_node, "clkreq-gpios", 1,
					 &clkreq_gpio);
	if (ret < 0) {
		pr_err("%s Failed to read clkreq gpio number, ret: %d\n",
		       __func__, ret);
		return ret;
	}

	ret = msm_gpio_mpm_wake_set(clkreq_gpio, true);
	if (ret < 0) {
		pr_err("%s Failed to setup clkreq gpio %u as wakeup capable, ret: %d\n",
		       __func__, clkreq_gpio, ret);
		return ret;
	}

	pr_info("%s clkreq gpio %u successfully setup for wakeup capable\n",
		__func__, clkreq_gpio);
	return 0;
}
