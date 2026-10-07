       IDENTIFICATION DIVISION.
       PROGRAM-ID. QRPAY9.
      * QR MERCHANT PAYMENT GATE
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-LIMIT                  PIC 9(9)V99 VALUE ZERO.
       01  WS-PROJ-BAL               PIC S9(9)V99 VALUE ZERO.
       01  WS-FAIL-REASON            PIC 9(3) VALUE ZERO.
       01  WS-POSTED                 PIC X(1) VALUE 'N'.
       01  WS-CARD-BLOCKED           PIC X(1) VALUE 'N'.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-LIMIT
           ACCEPT WS-PROJ-BAL
           ACCEPT WS-CARD-BLOCKED
           PERFORM 2000-VALIDATE
           IF WS-FAIL-REASON = ZERO
              PERFORM 3000-POST
           END-IF
           DISPLAY 'POSTED: ' WS-POSTED
           DISPLAY 'REASON: ' WS-FAIL-REASON
           STOP RUN.
       2000-VALIDATE.
           IF WS-CARD-BLOCKED = 'Y'
              MOVE 101 TO WS-FAIL-REASON
           END-IF
           IF WS-LIMIT >= WS-PROJ-BAL
              CONTINUE
           ELSE
              MOVE 102 TO WS-FAIL-REASON
           END-IF.
       3000-POST.
           MOVE 'Y' TO WS-POSTED.
