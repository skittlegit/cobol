       IDENTIFICATION DIVISION.
       PROGRAM-ID. GRVESC9.
      * COMPLAINT AGEING - ROUTE UNRESOLVED CASES TO OMBUDSMAN
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-COMPLAINT-ID           PIC X(8) VALUE SPACES.
       01  WS-AGE-DAYS               PIC 9(4) VALUE ZERO.
       01  WS-RESOLVED               PIC X(1) VALUE 'N'.
       01  WS-QUEUE                  PIC X(9) VALUE SPACES.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-COMPLAINT-ID
           ACCEPT WS-AGE-DAYS
           ACCEPT WS-RESOLVED
           PERFORM 2000-ROUTE
           DISPLAY 'QUEUE: ' WS-QUEUE
           STOP RUN.
       2000-ROUTE.
           IF WS-RESOLVED = 'Y'
              MOVE 'CLOSED' TO WS-QUEUE
           ELSE
              IF WS-AGE-DAYS > 30
                 MOVE 'OMBUDSMAN' TO WS-QUEUE
              ELSE
                 MOVE 'INTERNAL' TO WS-QUEUE
              END-IF
           END-IF.
