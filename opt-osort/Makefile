CC = cc
CFLAGS = -O2 -Wall -std=c11
LDLIBS = -lm

opt_osort: opt_osort.c
	$(CC) $(CFLAGS) -o $@ opt_osort.c $(LDLIBS)

.PHONY: clean
clean:
	rm -f opt_osort snippets.bin labels.txt
