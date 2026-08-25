       IDENTIFICATION DIVISION.
       PROGRAM-ID. T6V2P3B.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-COMPLAINT-DATE.
           05 WS-CMP-YEAR           PIC 9(4).
           05 WS-CMP-MONTH          PIC 99.
           05 WS-CMP-DAY            PIC 99.
       01  WS-DUE-DATE.
           05 WS-DUE-YEAR           PIC 9(4).
           05 WS-DUE-MONTH          PIC 99.
           05 WS-DUE-DAY            PIC 99.
       01  WS-DAYS-IN-MONTH         PIC 99.
       01  WS-LEAP-REMAINDER        PIC 999.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-COMPLAINT-DATE
           PERFORM 2000-ADD-CALENDAR-MONTH
           DISPLAY WS-DUE-DATE
           STOP RUN.
       2000-ADD-CALENDAR-MONTH.
           MOVE WS-CMP-YEAR TO WS-DUE-YEAR
           COMPUTE WS-DUE-MONTH = WS-CMP-MONTH + 1
           IF WS-DUE-MONTH > 12
              MOVE 1 TO WS-DUE-MONTH
              ADD 1 TO WS-DUE-YEAR
           END-IF
           MOVE 31 TO WS-DAYS-IN-MONTH
           IF WS-DUE-MONTH = 4 OR 6 OR 9 OR 11
              MOVE 30 TO WS-DAYS-IN-MONTH
           END-IF
           IF WS-DUE-MONTH = 2
              COMPUTE WS-LEAP-REMAINDER =
                      FUNCTION MOD(WS-DUE-YEAR 4)
              IF WS-LEAP-REMAINDER = 0
                 MOVE 29 TO WS-DAYS-IN-MONTH
              ELSE
                 MOVE 28 TO WS-DAYS-IN-MONTH
              END-IF
           END-IF
           MOVE WS-CMP-DAY TO WS-DUE-DAY
           IF WS-DUE-DAY > WS-DAYS-IN-MONTH
              MOVE WS-DAYS-IN-MONTH TO WS-DUE-DAY
           END-IF.
