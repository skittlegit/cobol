       IDENTIFICATION DIVISION.
       PROGRAM-ID. TPTR01.
      * TRUST CUSTOMER - WHICH PARTIES NEED BO IDENTIFICATION
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
           EVALUATE WS-ROLE
              WHEN 'AUTHOR'
              WHEN 'TRUSTEE'
              WHEN 'CONTROLLER'
                 MOVE 'Y' TO WS-IDENTIFY
              WHEN 'BENEFICIAR'
                 IF WS-INTEREST-PCT >= 15
                    MOVE 'Y' TO WS-IDENTIFY
                 END-IF
           END-EVALUATE.
