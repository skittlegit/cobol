       IDENTIFICATION DIVISION.
       PROGRAM-ID. LATEFEE1.
      *----------------------------------------------------------------
      * LATE PAYMENT CHARGE ASSESSMENT
      * REF: MD 2022 PARA 9(B)(V)
      *----------------------------------------------------------------
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-STMT-REC.
           05  WS-TOTAL-AMT-DUE      PIC 9(9)V99 VALUE ZERO.
           05  WS-OUTSTANDING-AMT    PIC 9(9)V99 VALUE ZERO.
           05  WS-DAYS-PAST-DUE      PIC 9(4) VALUE ZERO.
       01  WS-WORK-AREAS.
           05  WS-LATE-CHARGE        PIC 9(7)V99 VALUE ZERO.
           05  WS-LATE-RATE          PIC V999 VALUE .030.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-TOTAL-AMT-DUE
           ACCEPT WS-OUTSTANDING-AMT
           ACCEPT WS-DAYS-PAST-DUE
           PERFORM 2000-ASSESS
           DISPLAY 'CHARGE: ' WS-LATE-CHARGE
           STOP RUN.
       2000-ASSESS.
           IF WS-DAYS-PAST-DUE > 3
              COMPUTE WS-LATE-CHARGE ROUNDED
                      = WS-LATE-RATE * WS-TOTAL-AMT-DUE
           ELSE
              MOVE ZERO TO WS-LATE-CHARGE
           END-IF.
