       IDENTIFICATION DIVISION.
       PROGRAM-ID. TPTR04.
      * TRUST BENEFICIARY FILTER - SKIP SMALL INTERESTS
       DATA DIVISION.
       WORKING-STORAGE SECTION.
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
           MOVE 'N' TO WS-IDENTIFY
           IF WS-ROLE = 'AUTHOR' OR 'TRUSTEE' OR 'CONTROLLER'
                                 OR 'BENEFICIAR'
              MOVE 'Y' TO WS-IDENTIFY
           END-IF
           IF WS-ROLE = 'BENEFICIAR'
              IF WS-INTEREST-PCT < 15
                 MOVE 'N' TO WS-IDENTIFY
              END-IF
           END-IF.
