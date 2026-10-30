CC := gcc
CFLAGS := -Wall -Wextra -std=c11 -g -O0
SRC := $(wildcard src/*.c)
OBJ := $(SRC:.c=.o)
TARGET := debugger
OFFICIAL_TESTS := \
	tests/normal_test \
	tests/file_error \
	tests/invalid_fd \
	tests/permission_error \
	tests/system_call_error \
	tests/abnormal_exit \
	tests/segmentation_fault \
	tests/math_step \
	tests/function_call \
	tests/sigfpe_test \
	tests/nonzero_exit
LAUNCHER := ldst
AUTO_DIR := autodebug_src

.PHONY: all clean tests autodebug autodebug-tests run force

all: force $(TARGET) autodebug $(LAUNCHER) tests

force:

$(TARGET): $(OBJ)
	$(CC) $(CFLAGS) -o $@ $^

$(LAUNCHER): ldst.c
	$(CC) $(CFLAGS) -o $@ $<

src/%.o: src/%.c
	$(CC) $(CFLAGS) -c $< -o $@

autodebug: force
	$(MAKE) -f $(AUTO_DIR)/Makefile

autodebug-tests: tests

tests: $(OFFICIAL_TESTS)

tests/%: tests/%.c
	$(CC) $(CFLAGS) $< -o $@

run: all
	./ldst

clean:
	rm -f $(TARGET) $(LAUNCHER) $(OBJ) $(OFFICIAL_TESTS)
	$(MAKE) -f $(AUTO_DIR)/Makefile clean

debug: all
	./ldst
