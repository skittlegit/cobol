       IDENTIFICATION DIVISION.
       PROGRAM-ID. CLOSPEN3.
      *----------------------------------------------------------------
      * CLOSURE PENALTY - RS 500 PER CALENDAR DAY OF DELAY BEYOND
      * SEVEN WORKING DAYS. SLA WINDOW IN WORKING DAYS, ACCRUAL IN
      * CALENDAR DAYS.
      *----------------------------------------------------------------
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-INPUTS.
           05  WS-CAL-DAYS-ELAPSED   PIC 9(4) VALUE ZERO.
           05  WS-WORK-DAYS-ELAPSED  PIC 9(4) VALUE ZERO.
       01  WS-WORK-AREAS.
           05  WS-DELAY-CAL-DAYS     PIC S9(5) VALUE ZERO.
           05  WS-SLA-BREACH-DAY     PIC 9(4) VALUE ZERO.
           05  WS-PENALTY-AMT        PIC 9(7)V99 VALUE ZERO.
       01  WS-RPT-HEADING            PIC X(36)
           VALUE 'CLOSURE PENALTY REGISTER'.
       01  WS-PRINT-AREA.
           05  WS-PRINT-LINE OCCURS 66 PIC X(72).
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-CAL-DAYS-ELAPSED
           ACCEPT WS-WORK-DAYS-ELAPSED
           PERFORM 2000-PEN
           DISPLAY 'PENALTY: ' WS-PENALTY-AMT
           STOP RUN.
       2000-PEN.
           IF WS-WORK-DAYS-ELAPSED > 7
              COMPUTE WS-SLA-BREACH-DAY = WS-CAL-DAYS-ELAPSED
                      - (WS-WORK-DAYS-ELAPSED - 7)
              COMPUTE WS-DELAY-CAL-DAYS = WS-CAL-DAYS-ELAPSED
                      - WS-SLA-BREACH-DAY
              COMPUTE WS-PENALTY-AMT = 500 * WS-DELAY-CAL-DAYS
           ELSE
              MOVE ZERO TO WS-PENALTY-AMT
           END-IF.
