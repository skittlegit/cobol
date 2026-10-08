       IDENTIFICATION DIVISION.
       PROGRAM-ID. TPTR08.
      * TRUST BO - PARTY ROLE AND BENEFICIARY SHARE FROM UNITS
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-ROLE                   PIC X(10) VALUE SPACES.
       01  WS-UNITS-HELD             PIC 9(7) VALUE ZERO.
       01  WS-UNITS-TOTAL            PIC 9(7) VALUE 1.
       01  WS-SHARE-PCT              PIC 9(3)V99 VALUE ZERO.
       01  WS-IDENTIFY               PIC X VALUE 'N'.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-ROLE
           ACCEPT WS-UNITS-HELD
           ACCEPT WS-UNITS-TOTAL
           PERFORM 2000-SHARE
           DISPLAY 'IDENTIFY: ' WS-IDENTIFY
           STOP RUN.
       2000-SHARE.
           MOVE 'N' TO WS-IDENTIFY
           IF WS-ROLE = 'AUTHOR' OR 'TRUSTEE' OR 'CONTROLLER'
              MOVE 'Y' TO WS-IDENTIFY
           END-IF
           IF WS-ROLE = 'BENEFICIAR'
              COMPUTE WS-SHARE-PCT ROUNDED =
                      WS-UNITS-HELD * 100 / WS-UNITS-TOTAL
              IF WS-SHARE-PCT >= 15
                 MOVE 'Y' TO WS-IDENTIFY
              END-IF
           END-IF.
