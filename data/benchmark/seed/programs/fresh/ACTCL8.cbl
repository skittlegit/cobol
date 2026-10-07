       IDENTIFICATION DIVISION.
       PROGRAM-ID. ACTCL8.
      * UNACTIVATED CARD CLEAN-UP RUN
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-DAYS-ISSUED            PIC 9(4) VALUE ZERO.
       01  WS-USED                   PIC X(1) VALUE 'N'.
       01  WS-OUTCOME                PIC X(8) VALUE SPACES.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-DAYS-ISSUED
           ACCEPT WS-USED
           PERFORM 2000-CLEANUP
           DISPLAY 'OUTCOME: ' WS-OUTCOME
           STOP RUN.
       2000-CLEANUP.
           MOVE 'RETAIN' TO WS-OUTCOME
           IF WS-USED = 'N'
              IF WS-DAYS-ISSUED > 30
                 MOVE 'SEEKOTP' TO WS-OUTCOME
              END-IF
           END-IF
           DISPLAY 'CLEANUP DONE'.
