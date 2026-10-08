       IDENTIFICATION DIVISION.
       PROGRAM-ID. QGHT13.
      * HOTEL CHECK-OUT - LIMIT CHECK WITH CONSENT
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-LIMIT                  PIC 9(9)V99 VALUE ZERO.
       01  WS-PROJ-BAL               PIC S9(9)V99 VALUE ZERO.
       01  WS-OL-CONSENT             PIC X(1) VALUE 'N'.
       01  WS-CARD-STATUS            PIC X(1) VALUE 'A'.
       01  WS-FAIL-REASON            PIC 9(3) VALUE ZERO.
       01  WS-RESULT                 PIC X(8) VALUE SPACES.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-LIMIT
           ACCEPT WS-PROJ-BAL
           ACCEPT WS-OL-CONSENT
           ACCEPT WS-CARD-STATUS
           MOVE ZERO TO WS-FAIL-REASON
           PERFORM 2000-CHECKS
           IF WS-FAIL-REASON = ZERO
              MOVE 'APPROVED' TO WS-RESULT
           ELSE
              MOVE 'DECLINED' TO WS-RESULT
           END-IF
           DISPLAY 'RESULT: ' WS-RESULT ' ' WS-FAIL-REASON
           STOP RUN.
       2000-CHECKS.
           IF WS-CARD-STATUS NOT = 'A'
              MOVE 101 TO WS-FAIL-REASON
           END-IF
      * BREACHING THE LIMIT NEEDS EXPLICIT OVER-LIMIT CONSENT.
           IF WS-LIMIT >= WS-PROJ-BAL
              CONTINUE
           ELSE
              IF WS-OL-CONSENT NOT = 'Y'
                 MOVE 102 TO WS-FAIL-REASON
              END-IF
           END-IF.
