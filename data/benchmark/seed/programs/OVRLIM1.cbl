       IDENTIFICATION DIVISION.
       PROGRAM-ID. OVRLIM1.
      *----------------------------------------------------------------
      * BATCH CREDIT-LIMIT VALIDATION WITH CARDHOLDER CONSENT LOOKUP
      *----------------------------------------------------------------
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-TRANSACTION.
           05  WS-PROJECTED-BAL       PIC 9(7) VALUE ZERO.
           05  WS-CREDIT-LIMIT        PIC 9(7) VALUE ZERO.
       01  WS-CONSENT-STATE.
           05  WS-CONSENT-REC-FOUND   PIC X(1) VALUE 'N'.
           05  WS-CONSENT-ON-FILE     PIC X(1) VALUE 'N'.
       01  WS-CONTROL.
           05  WS-MORE-TRANSACTIONS   PIC X(1) VALUE 'Y'.
           05  WS-VALID               PIC X(1) VALUE 'N'.
           05  WS-POSTED              PIC X(1) VALUE 'N'.
       PROCEDURE DIVISION.
       1000-PROCESS-BATCH.
           PERFORM UNTIL WS-MORE-TRANSACTIONS NOT = 'Y'
              ACCEPT WS-PROJECTED-BAL
              ACCEPT WS-CREDIT-LIMIT
              ACCEPT WS-CONSENT-REC-FOUND
              MOVE 'N' TO WS-POSTED
              MOVE 'N' TO WS-CONSENT-ON-FILE
              PERFORM 1500-LOAD-CONSENT
              PERFORM 2000-VALIDATE-LIMIT
              IF WS-VALID = 'Y'
                 PERFORM 3000-POST-TRANSACTION
              END-IF
              DISPLAY 'POSTED: ' WS-POSTED
              ACCEPT WS-MORE-TRANSACTIONS
           END-PERFORM
           STOP RUN.
       1500-LOAD-CONSENT.
           IF WS-CONSENT-REC-FOUND = 'Y'
              MOVE 'Y' TO WS-CONSENT-ON-FILE
           END-IF.
       2000-VALIDATE-LIMIT.
           MOVE 'Y' TO WS-VALID
           IF WS-PROJECTED-BAL > WS-CREDIT-LIMIT
              IF WS-CONSENT-ON-FILE NOT = 'Y'
                 MOVE 'N' TO WS-VALID
              END-IF
           END-IF.
       3000-POST-TRANSACTION.
           MOVE 'Y' TO WS-POSTED.
