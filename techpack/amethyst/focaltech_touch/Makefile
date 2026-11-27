# SPDX-License-Identifier: GPL-2.0-only
# Out-of-tree build for LineageOS's kernel.mk (TARGET_KERNEL_EXT_MODULES).
# Its only module dependency, xiaomi_touch, is an in-tree kernel module, so
# no KBUILD_EXTRA_SYMBOLS are needed.

all: modules

%:
	$(MAKE) -C $(KERNEL_SRC) M=$(M) $@ $(KBUILD_OPTIONS)
