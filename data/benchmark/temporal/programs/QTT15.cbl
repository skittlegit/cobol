       IDENTIFICATION DIVISION.
       PROGRAM-ID. QTT15.
      * TRUST BENEFICIARY - SHARE FROM UNITS, EXACT
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-ROLE                   PIC X(1) VALUE SPACE.
       01  WS-UNITS-HELD             PIC 9(7) VALUE ZERO.
       01  WS-UNITS-TOTAL            PIC 9(7) VALUE 1.
       01  WS-IDENTIFY               PIC X(1) VALUE 'N'.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-ROLE
           ACCEPT WS-UNITS-HELD
           ACCEPT WS-UNITS-TOTAL
           PERFORM 2000-PARTY
           DISPLAY 'IDENTIFY: ' WS-IDENTIFY
           STOP RUN.
       2000-PARTY.
           MOVE 'N' TO WS-IDENTIFY
           EVALUATE TRUE
              WHEN WS-ROLE = 'A' OR WS-ROLE = 'T' OR WS-ROLE = 'C'
                 MOVE 'Y' TO WS-IDENTIFY
              WHEN WS-ROLE = 'B'
                 AND WS-UNITS-HELD * 100 >= 15 * WS-UNITS-TOTAL
                 MOVE 'Y' TO WS-IDENTIFY
           END-EVALUATE.
