CC = gcc
CFLAGS = -Wall -Wextra -g -O0 -std=c11

all: app_debug

app_debug: main.o calc.o
	$(CC) $(CFLAGS) -o $@ $^

main.o: main.c calc.h
	$(CC) $(CFLAGS) -c $< -o $@

calc.o: calc.c calc.h
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f *.o app_debug

.PHONY: all clean
