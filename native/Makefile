CC ?= gcc
CFLAGS ?= -Wall -Wextra -std=c11 -fPIC -O2 -g

all: libldstnative.so

libldstnative.so: process_launcher.o process_status.o signal_handler.o
	$(CC) -shared -o $@ $^

process_launcher.o: process_launcher.c
	$(CC) $(CFLAGS) -c $< -o $@

process_status.o: process_status.c
	$(CC) $(CFLAGS) -c $< -o $@

signal_handler.o: signal_handler.c
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f *.o *.so

.PHONY: all clean
