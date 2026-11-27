/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * Adapts the donor driver (written for the popsicle-w-oss xiaomi_touch) to
 * the in-tree amethyst xiaomi_touch (warsaw-w-oss framework,
 * drivers/input/touchscreen/xiaomi).
 *
 * The popsicle framework spells the touch-mode enum as DATA_MODE_<n>; the
 * in-tree one uses descriptive names. The numeric values are the protocol
 * shared with the THP HAL and with xiaomi_touch's mode table, so every
 * mapping below keeps the popsicle numeric value (noted in each comment) and
 * names the in-tree enumerator that has that value.
 */
#ifndef __FOCALTECH_AMETHYST_COMPAT_H__
#define __FOCALTECH_AMETHYST_COMPAT_H__

#include <linux/errno.h>
#include "xiaomi_touch.h"

#define DATA_MODE_0	Touch_Game_Mode			/* 0 */
#define DATA_MODE_1	Touch_Active_MODE		/* 1 */
#define DATA_MODE_2	Touch_UP_THRESHOLD		/* 2 */
#define DATA_MODE_3	Touch_Tolerance			/* 3 */
#define DATA_MODE_4	Touch_Aim_Sensitivity		/* 4 */
#define DATA_MODE_5	Touch_Tap_Stability		/* 5 */
#define DATA_MODE_6	Touch_Expert_Mode		/* 6 */
#define DATA_MODE_7	Touch_Edge_Filter		/* 7 */
#define DATA_MODE_8	Touch_Panel_Orientation		/* 8 */
#define DATA_MODE_9	Touch_Report_Rate		/* 9 */
#define DATA_MODE_10	Touch_Fod_Enable		/* 10 */
#define DATA_MODE_11	Touch_Aod_Enable		/* 11 */
#define DATA_MODE_14	Touch_Doubletap_Mode		/* 14 */
#define DATA_MODE_17	Touch_Nonui_Mode		/* 17 */
#define DATA_MODE_25	Touch_Is_In_Input_Method	/* 25 */
/*
 * 44: popsicle's "sensor tap" (weak double tap). The in-tree mode table
 * ends at Touch_Mode_NUM (42), so driver_get_touch_mode() returns -1 for it
 * and the feature stays off.
 */
#define DATA_MODE_44	44
/* popsicle's mode-table size; the in-tree API uses Touch_Mode_NUM. */
#define DATA_MODE_45	Touch_Mode_NUM
#define DATA_MODE_52	Touch_Boost_EN			/* 200 */
#define DATA_MODE_53	Touch_Empty_Int			/* 201 */
#define DATA_MODE_54	Touch_Super_Report		/* 202 */
#define DATA_MODE_62	THP_LOCK_SCAN_MODE		/* 1000 */
#define DATA_MODE_63	THP_FOD_DOWNUP_CTL		/* 1001 */
#define DATA_MODE_66	THP_HAL_INIT_READY		/* 1004 */
#define DATA_MODE_73	THP_HAL_REPORT_RATE		/* 1011 */
#define DATA_MODE_133	THP_IDLE_BASALINE_UPDATE	/* 1071 */
#define DATA_MODE_138	Touch_THP_Dump			/* 1076 */
#define DATA_MODE_146	THP_IDLE_THD			/* 1084 */
#define DATA_MODE_153	THP_BASE_STATUS			/* 1091 */
#define DATA_MODE_160	THP_IC_FREQ_HOPPING		/* 1098 */
#define DATA_MODE_161	THP_IC_CALIBRATION		/* 1099 */
#define DATA_MODE_165	THP_IC_GESTRUE_FEEDBACK		/* 1103 */
/* 1114: weak-double-tap report; no in-tree enumerator (see below). */
#define DATA_MODE_177	(THP_CMD_BASE + 114)
#define DATA_MODE_178	Touch_GAMETURBOTOOL_FOLLOWUP	/* 10001, boost notify to HAL */

/* THP IC command ids (enum THP_IC_MODE_TYPE) */
#define IC_MODE_44	SET_OPEN_TRANSPORT_MODE		/* 3045 */
#define IC_MODE_49	SET_TOUCH_IC_INFO		/* 3050 */

/*
 * The popsicle framework exports update_weak_doubletap_value(); the in-tree
 * framework has no equivalent, so weak-double-tap events cannot be passed
 * on. Report that instead of pretending to succeed.
 */
static inline int update_weak_doubletap_value(int value)
{
	return -EOPNOTSUPP;
}

#endif /* __FOCALTECH_AMETHYST_COMPAT_H__ */
