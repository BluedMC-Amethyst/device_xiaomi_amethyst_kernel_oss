#
# Build the Amethyst DTB image (vendor_boot --dtb) and dtbo.img from the
# sources in this directory, inside the LineageOS build.
#
# Hooked in through LineageOS kernel.mk:
#   BOARD_CUSTOM_DTBIMG_MK  := <kernel>/arch/arm64/boot/dts/amethyst/amethyst-dt.mk
#   BOARD_CUSTOM_DTBOIMG_MK := <same file>
# with TARGET_NEEDS_DTBOIMAGE := true and BOARD_INCLUDE_DTB_IN_BOOTIMG := true,
# and without BOARD_PREBUILT_DTBIMAGE_DIR (BOARD_PREBUILT_DTBOIMAGE keeps its
# BoardConfigKernel.mk default, the rule target below).
#
# kernel.mk includes this file from both hooks; the guard makes the second
# include a no-op. See docs/amethyst-drivers/devicetree.md.
#

ifndef AMETHYST_DT_MK_INCLUDED
AMETHYST_DT_MK_INCLUDED := true

AMETHYST_DT_SRC := $(patsubst %/,%,$(dir $(lastword $(MAKEFILE_LIST))))
AMETHYST_DT_KERNEL := $(abspath $(AMETHYST_DT_SRC)/../../../../..)
AMETHYST_DT_OUT := $(TARGET_OUT_INTERMEDIATES)/AMETHYST_DT_OBJ
AMETHYST_DT_TOOLS := \
    $(HOST_OUT_EXECUTABLES)/dtc \
    $(HOST_OUT_EXECUTABLES)/fdtoverlay \
    $(HOST_OUT_EXECUTABLES)/fdtoverlaymerge \
    $(HOST_OUT_EXECUTABLES)/fdtget \
    $(HOST_OUT_EXECUTABLES)/fdtput \
    $(HOST_OUT_EXECUTABLES)/ufdt_apply_overlay
AMETHYST_DT_SCRIPTS := \
    $(AMETHYST_DT_KERNEL)/scripts/amethyst-dt-build.py \
    $(AMETHYST_DT_KERNEL)/scripts/amethyst-merge_dtbs.py
AMETHYST_DT_INPUTS := $(shell find $(AMETHYST_DT_SRC) -type f \
    \( -name '*.dts' -o -name '*.dtsi' -o -name '*.h' -o -name '*.json' \))
# Same preprocessor the stock images were built with.
AMETHYST_DT_CPP ?= $(TARGET_KERNEL_CLANG_PATH)/bin/clang

$(AMETHYST_DT_OUT)/dtb.img: $(AMETHYST_DT_INPUTS) $(AMETHYST_DT_SCRIPTS) $(AMETHYST_DT_TOOLS)
	@echo "Building Amethyst DTB and DTBO images"
	$(hide) rm -rf $(AMETHYST_DT_OUT)
	$(hide) python3 $(AMETHYST_DT_KERNEL)/scripts/amethyst-dt-build.py \
		--manifest $(AMETHYST_DT_SRC)/amethyst-dt.json \
		--out $(AMETHYST_DT_OUT) \
		--tools $(abspath $(HOST_OUT_EXECUTABLES)) \
		--cpp $(AMETHYST_DT_CPP)

$(AMETHYST_DT_OUT)/dtbo.img: $(AMETHYST_DT_OUT)/dtb.img
	$(hide) test -f $@

$(INSTALLED_DTBIMAGE_TARGET): $(AMETHYST_DT_OUT)/dtb.img
	$(hide) mkdir -p $(dir $@)
	cp $< $@

$(BOARD_PREBUILT_DTBOIMAGE): $(AMETHYST_DT_OUT)/dtbo.img
	$(hide) mkdir -p $(dir $@)
	cp $< $@

.PHONY: amethyst-dt
amethyst-dt: $(INSTALLED_DTBIMAGE_TARGET) $(BOARD_PREBUILT_DTBOIMAGE)

endif # AMETHYST_DT_MK_INCLUDED
