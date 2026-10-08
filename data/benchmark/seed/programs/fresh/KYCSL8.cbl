       IDENTIFICATION DIVISION.
       PROGRAM-ID. KYCSL8.
      * KYC RECORD SYNC STATUS AFTER CUSTOMER UPDATE
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-CHANGE-DAY             PIC 9(5) VALUE ZERO.
       01  WS-TODAY                  PIC 9(5) VALUE ZERO.
       01  WS-AGE                    PIC S9(5) VALUE ZERO.
       01  WS-SYNC                   PIC X(8) VALUE SPACES.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-CHANGE-DAY
           ACCEPT WS-TODAY
           PERFORM 2000-SYNC
           DISPLAY 'SYNC: ' WS-SYNC
           STOP RUN.
       2000-SYNC.
           COMPUTE WS-AGE = WS-TODAY - WS-CHANGE-DAY
           MOVE 'QUEUED' TO WS-SYNC
           IF WS-AGE > 7
              MOVE 'BREACH' TO WS-SYNC
           END-IF
           DISPLAY 'SYNC CHECKED'.
