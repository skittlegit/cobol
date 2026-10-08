       IDENTIFICATION DIVISION.
       PROGRAM-ID. QTT11.
      * TRUST PARTIES - ROLE CODE AND INTEREST
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-ROLE-CODE              PIC 9 VALUE ZERO.
       01  WS-INTEREST               PIC 9(3)V99 VALUE ZERO.
       01  WS-IDENTIFY               PIC X(1) VALUE 'N'.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-ROLE-CODE
           ACCEPT WS-INTEREST
           PERFORM 2000-PARTY
           DISPLAY 'IDENTIFY: ' WS-IDENTIFY
           STOP RUN.
       2000-PARTY.
      * 1 AUTHOR, 2 TRUSTEE, 3 CONTROLLER, 4 BENEFICIARY.
           MOVE 'N' TO WS-IDENTIFY
           EVALUATE WS-ROLE-CODE
              WHEN 1 THRU 3
                 MOVE 'Y' TO WS-IDENTIFY
              WHEN 4
                 IF WS-INTEREST >= 15
                    MOVE 'Y' TO WS-IDENTIFY
                 END-IF
           END-EVALUATE.
