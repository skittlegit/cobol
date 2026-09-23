       IDENTIFICATION DIVISION.
       PROGRAM-ID. CLOSPEN4.
      *----------------------------------------------------------------
      * ACCOUNT CLOSURE PROCESSOR - VALIDATES DUES AND MARKS CLOSED
      *----------------------------------------------------------------
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-INPUTS.
           05  WS-OUTSTANDING        PIC 9(9)V99 VALUE ZERO.
           05  WS-ELAPSED-DAYS       PIC 9(4) VALUE ZERO.
       01  WS-STATUS-AREAS.
           05  WS-CLOSE-STATUS       PIC X(8) VALUE SPACES.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-OUTSTANDING
           ACCEPT WS-ELAPSED-DAYS
           PERFORM 2000-CLOSE-ACCT
           DISPLAY 'STATUS: ' WS-CLOSE-STATUS
           STOP RUN.
       2000-CLOSE-ACCT.
           IF WS-OUTSTANDING > ZERO
              MOVE 'BLOCKED' TO WS-CLOSE-STATUS
           ELSE
              MOVE 'CLOSED' TO WS-CLOSE-STATUS
           END-IF.
      * NOTE: SLA TRACKING TBD
