       IDENTIFICATION DIVISION.
       PROGRAM-ID. TPTR02.
      * TRUST BO - BENEFICIARY INTEREST FLOOR
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-TRUST-FLOOR            PIC 9(3)V99 VALUE 15.00.
       01  WS-ROLE                   PIC X(10) VALUE SPACES.
       01  WS-INTEREST-PCT           PIC 9(3)V99 VALUE ZERO.
       01  WS-IDENTIFY               PIC X VALUE 'N'.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-ROLE
           ACCEPT WS-INTEREST-PCT
           PERFORM 2000-TRUST-PARTY
           DISPLAY 'IDENTIFY: ' WS-IDENTIFY
           STOP RUN.
       2000-TRUST-PARTY.
           IF WS-ROLE = 'AUTHOR' OR WS-ROLE = 'TRUSTEE'
              OR WS-ROLE = 'CONTROLLER'
              MOVE 'Y' TO WS-IDENTIFY
           ELSE
              IF WS-ROLE = 'BENEFICIAR'
                 AND WS-INTEREST-PCT NOT < WS-TRUST-FLOOR
                 MOVE 'Y' TO WS-IDENTIFY
              ELSE
                 MOVE 'N' TO WS-IDENTIFY
              END-IF
           END-IF.
