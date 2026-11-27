# SPDX-License-Identifier: GPL-2.0-only
# Out-of-tree build for LineageOS's kernel.mk (TARGET_KERNEL_EXT_MODULES).

all: modules

%:
	$(MAKE) -C $(KERNEL_SRC) M=$(M) $@ $(KBUILD_OPTIONS)
