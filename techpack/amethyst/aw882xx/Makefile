# SPDX-License-Identifier: GPL-2.0-only
# Out-of-tree build for LineageOS's kernel.mk (TARGET_KERNEL_EXT_MODULES).
# machine_dlkm (MiCode audio-kernel) provides the smart PA hooks.
KBUILD_OPTIONS += KBUILD_EXTRA_SYMBOLS=$(OUT_DIR)/../sm7635-modules/qcom/opensource/audio-kernel/Module.symvers

all: modules

%:
	$(MAKE) -C $(KERNEL_SRC) M=$(M) $@ $(KBUILD_OPTIONS)
