CC := gcc
CFLAGS := -Wall -Wextra -std=c11 -g
SRC := $(wildcard src/*.c)
OBJ := $(SRC:.c=.o)
TARGET := debugger
TEST_SRC := $(wildcard tests/*.c)
TEST_BIN := $(TEST_SRC:.c=)

.PHONY: all clean tests run

all: $(TARGET)

$(TARGET): $(OBJ)
	$(CC) $(CFLAGS) -o $@ $^

src/%.o: src/%.c
	$(CC) $(CFLAGS) -c $< -o $@

tests: $(TEST_BIN)

tests/%: tests/%.c
	$(CC) $(CFLAGS) $< -o $@

run: $(TARGET) tests
	./$(TARGET) ./tests/normal_test

clean:
	rm -f $(TARGET) $(OBJ) $(TEST_BIN)
	rm -f logs/*.txt results/*.txt
