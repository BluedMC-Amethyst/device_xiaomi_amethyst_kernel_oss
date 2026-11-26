/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef _XIAOMI_HWID_H
#define _XIAOMI_HWID_H

#include <linux/types.h>

/* Values verified against the Amethyst hwid, Wi-Fi and USBSS modules. */
enum hw_country_version {
	CountryCN = 0,
	CountryGlobal = 1,
	CountryIndia = 2,
};

enum hw_project_version {
	/*
	 * Amethyst is O16U. The other projects only select code paths for
	 * other phones in MiCode's shared drivers (cnss2, icnss2, usbss).
	 * Values 1-11 are from Xiaomi's SM8650 drivers/misc/hwid/hwid.h.
	 */
	HARDWARE_PROJECT_N1 = 1,	/* aurora */
	HARDWARE_PROJECT_N2 = 2,	/* shennong */
	HARDWARE_PROJECT_N3 = 3,	/* houji */
	HARDWARE_PROJECT_N8 = 4,	/* ruyi */
	HARDWARE_PROJECT_N11U = 5,	/* manet */
	/* Stock amethyst kernel value; differs from SM8650 (6). */
	HARDWARE_PROJECT_N18 = 7,	/* goku */
	HARDWARE_PROJECT_O11 = 7,	/* zorn */
	HARDWARE_PROJECT_N16T = 8,	/* peridot */
	HARDWARE_PROJECT_N9 = 9,	/* chenfeng */
	HARDWARE_PROJECT_O81 = 10,	/* muyu */
	HARDWARE_PROJECT_O82 = 11,	/* uke */
	HARDWARE_PROJECT_O16U = 12,	/* amethyst */
	HARDWARE_PROJECT_P16U = 14,
	/* Value unpublished; never reported by Amethyst's hwid. */
	HARDWARE_PROJECT_N801 = 0x7fffffff,
};

const char *product_name_get(void);
uint32_t get_hw_project_adc(void);
uint32_t get_hw_build_adc(void);
uint32_t get_hw_version_platform(void);
uint32_t get_hw_id_value(void);
uint32_t get_hw_country_version(void);
uint32_t get_hw_version_major(void);
uint32_t get_hw_version_minor(void);
uint32_t get_hw_version_build(void);

#endif /* _XIAOMI_HWID_H */
