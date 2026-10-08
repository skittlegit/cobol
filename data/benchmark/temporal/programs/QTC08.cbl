       IDENTIFICATION DIVISION.
       PROGRAM-ID. QTC08.
      * COMPANY BO - ONE PARAGRAPH PER ROUTE
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-SHARES                 PIC 9(3)V99 VALUE ZERO.
       01  WS-CAPITAL                PIC 9(3)V99 VALUE ZERO.
       01  WS-PROFITS                PIC 9(3)V99 VALUE ZERO.
       01  WS-OTHER-CONTROL          PIC X(1) VALUE 'N'.
       01  WS-IS-BO                  PIC X(1) VALUE 'N'.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-SHARES
           ACCEPT WS-CAPITAL
           ACCEPT WS-PROFITS
           ACCEPT WS-OTHER-CONTROL
           PERFORM 2000-OWNERSHIP
           PERFORM 3000-CONTROL
           DISPLAY 'BO: ' WS-IS-BO
           STOP RUN.
       2000-OWNERSHIP.
           IF WS-SHARES > 25.00 OR WS-CAPITAL > 25.00
              OR WS-PROFITS > 25.00
              MOVE 'Y' TO WS-IS-BO
           END-IF.
       3000-CONTROL.
           IF WS-OTHER-CONTROL = 'Y'
              MOVE 'Y' TO WS-IS-BO
           END-IF.
