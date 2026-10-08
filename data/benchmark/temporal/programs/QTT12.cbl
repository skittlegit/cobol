       IDENTIFICATION DIVISION.
       PROGRAM-ID. QTT12.
      * TRUST DEED REVIEW - PARTIES TO IDENTIFY
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       COPY QTT12P.
       01  WS-PARTIES.
           05  WS-PARTY OCCURS 5 TIMES.
               10  WS-P-ROLE        PIC X(1).
               10  WS-P-PCT         PIC 9(3)V99.
       01  WS-IX                     PIC 9 VALUE ZERO.
       01  WS-COUNT                  PIC 9 VALUE ZERO.
       PROCEDURE DIVISION.
       1000-MAIN.
           PERFORM VARYING WS-IX FROM 1 BY 1 UNTIL WS-IX > 5
              ACCEPT WS-P-ROLE (WS-IX)
              ACCEPT WS-P-PCT (WS-IX)
           END-PERFORM
           PERFORM 2000-COUNT
           DISPLAY 'TO IDENTIFY: ' WS-COUNT
           STOP RUN.
       2000-COUNT.
      * ROLES: A AUTHOR, T TRUSTEE, C CONTROLLER, B BENEFICIARY.
           MOVE ZERO TO WS-COUNT
           PERFORM VARYING WS-IX FROM 1 BY 1 UNTIL WS-IX > 5
              IF WS-P-ROLE (WS-IX) = 'A' OR 'T' OR 'C'
                 ADD 1 TO WS-COUNT
              END-IF
              IF WS-P-ROLE (WS-IX) = 'B'
                 AND WS-P-PCT (WS-IX) >= TP-BENEF-MIN-PCT
                 ADD 1 TO WS-COUNT
              END-IF
           END-PERFORM.
