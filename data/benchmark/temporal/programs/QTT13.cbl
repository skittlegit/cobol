       IDENTIFICATION DIVISION.
       PROGRAM-ID. QTT13.
      * TRUST ONBOARDING - CALLS THE BENEFICIARY RULE
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-ROLE                   PIC X(1) VALUE SPACE.
       01  WS-INTEREST               PIC 9(3)V99 VALUE ZERO.
       01  WS-IDENTIFY               PIC X(1) VALUE 'N'.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-ROLE
           ACCEPT WS-INTEREST
           IF WS-ROLE = 'B'
              CALL 'QTT13K' USING WS-INTEREST WS-IDENTIFY
           ELSE
              IF WS-ROLE = 'A' OR 'T' OR 'C'
                 MOVE 'Y' TO WS-IDENTIFY
              END-IF
           END-IF
           DISPLAY 'IDENTIFY: ' WS-IDENTIFY
           STOP RUN.
