       IDENTIFICATION DIVISION.
       PROGRAM-ID. CLOSPN5D.
      *----------------------------------------------------------------
      * CLOSURE PROCESSOR WITH PENALTY MODULE (PILOT - DISABLED)
      *----------------------------------------------------------------
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-FLAGS.
           05  WS-PEN-ENABLED        PIC X(1) VALUE 'N'.
               88  PENALTY-ON        VALUE 'Y'.
       01  WS-INPUTS.
           05  WS-ELAPSED-DAYS       PIC 9(4) VALUE ZERO.
       01  WS-WORK-AREAS.
           05  WS-DELAY-DAYS         PIC S9(5) VALUE ZERO.
           05  WS-PENALTY-AMT        PIC 9(7)V99 VALUE ZERO.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-ELAPSED-DAYS
           IF PENALTY-ON
              PERFORM 2000-PENALTY
           END-IF
           DISPLAY 'PENALTY: ' WS-PENALTY-AMT
           STOP RUN.
       2000-PENALTY.
           COMPUTE WS-DELAY-DAYS = WS-ELAPSED-DAYS - 7
           IF WS-DELAY-DAYS > ZERO
              COMPUTE WS-PENALTY-AMT = 500 * WS-DELAY-DAYS
           END-IF.
