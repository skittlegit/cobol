       IDENTIFICATION DIVISION.
       PROGRAM-ID. QTT17.
      * TRUST - BENEFICIARY FLOOR CONSTANT
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-BENEF-FLOOR            PIC 9(3)V99 VALUE 15.00.
       01  WS-ROLE                   PIC X(1) VALUE SPACE.
       01  WS-INTEREST               PIC 9(3)V99 VALUE ZERO.
       01  WS-IDENTIFY               PIC X(1) VALUE 'N'.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-ROLE
           ACCEPT WS-INTEREST
           PERFORM 2000-PARTY
           DISPLAY 'IDENTIFY: ' WS-IDENTIFY
           STOP RUN.
       2000-PARTY.
           EVALUATE WS-ROLE
              WHEN 'A'
              WHEN 'T'
              WHEN 'C'
                 MOVE 'Y' TO WS-IDENTIFY
              WHEN 'B'
                 IF WS-INTEREST < WS-BENEF-FLOOR
                    MOVE 'N' TO WS-IDENTIFY
                 ELSE
                    MOVE 'Y' TO WS-IDENTIFY
                 END-IF
              WHEN OTHER
                 MOVE 'N' TO WS-IDENTIFY
           END-EVALUATE.
