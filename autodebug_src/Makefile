CC := gcc
CFLAGS := -Wall -Wextra -std=c11 -g
SRC := $(wildcard autodebug_src/*.c)
OBJ := $(SRC:.c=.o)
TARGET := autodebug
OFFICIAL_TESTS := \
	tests/normal_test \
	tests/file_error \
	tests/invalid_fd \
	tests/permission_error \
	tests/system_call_error \
	tests/abnormal_exit \
	tests/segmentation_fault

.PHONY: all clean tests force

all: force $(TARGET)

force:

$(TARGET): $(OBJ)
	$(CC) $(CFLAGS) -o $@ $^

autodebug_src/%.o: autodebug_src/%.c
	$(CC) $(CFLAGS) -c $< -o $@

tests: $(OFFICIAL_TESTS)

tests/%: tests/%.c
	$(CC) $(CFLAGS) $< -o $@

clean:
	rm -f $(TARGET) $(OBJ)
	rm -f logs/autodebug_*.txt results/autodebug_report.txt
