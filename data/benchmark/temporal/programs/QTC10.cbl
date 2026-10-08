       IDENTIFICATION DIVISION.
       PROGRAM-ID. QTC10.
      * COMPANY BO - REASON CODE FOR THE CDD FILE
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-SHARES                 PIC 9(3)V99 VALUE ZERO.
       01  WS-CAPITAL                PIC 9(3)V99 VALUE ZERO.
       01  WS-PROFITS                PIC 9(3)V99 VALUE ZERO.
       01  WS-OTHER-CONTROL          PIC X(1) VALUE 'N'.
       01  WS-THRESHOLD              PIC 9(3)V99 VALUE 25.00.
       01  WS-REASON                 PIC X(1) VALUE SPACE.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-SHARES
           ACCEPT WS-CAPITAL
           ACCEPT WS-PROFITS
           ACCEPT WS-OTHER-CONTROL
           PERFORM 2000-REASON
           DISPLAY 'REASON: ' WS-REASON
           STOP RUN.
       2000-REASON.
      * S/C/P = OWNERSHIP ROUTE, K = CONTROL, N = NOT A BO.
           MOVE 'N' TO WS-REASON
           IF WS-OTHER-CONTROL = 'Y'
              MOVE 'K' TO WS-REASON
           END-IF
           IF WS-PROFITS > WS-THRESHOLD
              MOVE 'P' TO WS-REASON
           END-IF
           IF WS-CAPITAL > WS-THRESHOLD
              MOVE 'C' TO WS-REASON
           END-IF
           IF WS-SHARES > WS-THRESHOLD
              MOVE 'S' TO WS-REASON
           END-IF.
