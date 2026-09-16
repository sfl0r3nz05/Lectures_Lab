# DEMO 4: DATA CORRELATION

---

## Case 1: Running a SEC interactively

> Input file is STDIN

```bash
./sec --conf=rules/echo.sec --input=-
```

 - Input:

 ```string
 This is a test event
 ```

 - Output:

 ```string
 Wed Sep 16 04:14:52 2026: This is a test event
 ```

---

## Case 2: Write to a file

> Input file is STDIN

```bash
./sec --conf=/rules/write-to-file.sec --input=-
```

 - Input:

 ```string
 AAABBBCCCDDDEEE
 BBBBAAAACCCCCCC
 CCCCCCCAAAAEEEE
 ```

 - Output:

 ```string
 Wed Sep 16 04:49:41 2026: three A characters were observed
 Wed Sep 16 04:49:41 2026: three A characters were observed
 Wed Sep 16 04:49:41 2026: three A characters were observed
 ```

## Case 3: Rule application order

> Input file is STDIN

```bash
sec --conf=/rules/ltr1.sec --input=-
```

 - Input:

 ```string
 AAABBBCCCDDDEEE
 ```

 - Output (Only AAA):

 ```string
 three A characters were observed
 ```

> Add `continue= TakeNext` to `pattern= AAA`

```bash
sec --conf=/rules/ltr1.sec --input=-
```

 - Input:

 ```string
 AAABBBCCCDDDEEE
 ```

 - Output (Only AAA):

 ```string
 three A characters were observed
 three B characters were observed
 ```

> Add ltr2.sec

```bash
sec --conf=/rules/ltr1.sec  --conf=/rules/ltr2.sec --input=-
```

 - Input:

 ```string
 AAABBBCCCDDDEEE
 ```

 - Output (Only AAA):

 ```string
 three A characters were observed
 three B characters were observed
 three C characters were observed
 three E characters were observed
 ```
