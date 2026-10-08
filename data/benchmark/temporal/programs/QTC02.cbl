       IDENTIFICATION DIVISION.
       PROGRAM-ID. QTC02.
      * COMPANY BO - LARGEST INTEREST AGAINST THE LIMIT
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-SHARES                 PIC 9(3)V99 VALUE ZERO.
       01  WS-CAPITAL                PIC 9(3)V99 VALUE ZERO.
       01  WS-PROFITS                PIC 9(3)V99 VALUE ZERO.
       01  WS-LARGEST                PIC 9(3)V99 VALUE ZERO.
       01  WS-OWN-LIMIT              PIC 9(3)V99 VALUE 25.00.
       01  WS-OTHER-CONTROL          PIC X(1) VALUE 'N'.
       01  WS-IS-BO                  PIC X(1) VALUE 'N'.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-SHARES
           ACCEPT WS-CAPITAL
           ACCEPT WS-PROFITS
           ACCEPT WS-OTHER-CONTROL
           PERFORM 2000-TEST
           DISPLAY 'BO: ' WS-IS-BO
           STOP RUN.
       2000-TEST.
           COMPUTE WS-LARGEST =
                   FUNCTION MAX (WS-SHARES WS-CAPITAL WS-PROFITS)
           IF WS-LARGEST > WS-OWN-LIMIT OR WS-OTHER-CONTROL = 'Y'
              MOVE 'Y' TO WS-IS-BO
           ELSE
              MOVE 'N' TO WS-IS-BO
           END-IF.
