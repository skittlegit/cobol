       IDENTIFICATION DIVISION.
       PROGRAM-ID. TPTR07.
      * TRUST PARTY LIST - COUNT PERSONS TO IDENTIFY
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-PARTIES.
           05  WS-PARTY OCCURS 6 TIMES.
               10  WS-PARTY-ROLE    PIC X(10).
               10  WS-PARTY-PCT     PIC 9(3)V99.
       01  WS-IX                     PIC 9 VALUE ZERO.
       01  WS-TO-IDENTIFY            PIC 9 VALUE ZERO.
       PROCEDURE DIVISION.
       1000-MAIN.
           PERFORM VARYING WS-IX FROM 1 BY 1 UNTIL WS-IX > 6
              ACCEPT WS-PARTY-ROLE (WS-IX)
              ACCEPT WS-PARTY-PCT (WS-IX)
           END-PERFORM
           PERFORM 2000-SCAN
           DISPLAY 'PARTIES TO IDENTIFY: ' WS-TO-IDENTIFY
           STOP RUN.
       2000-SCAN.
           MOVE ZERO TO WS-TO-IDENTIFY
           PERFORM VARYING WS-IX FROM 1 BY 1 UNTIL WS-IX > 6
              EVALUATE WS-PARTY-ROLE (WS-IX)
                 WHEN 'AUTHOR'
                 WHEN 'TRUSTEE'
                 WHEN 'CONTROLLER'
                    ADD 1 TO WS-TO-IDENTIFY
                 WHEN 'BENEFICIAR'
                    IF WS-PARTY-PCT (WS-IX) >= 15.00
                       ADD 1 TO WS-TO-IDENTIFY
                    END-IF
              END-EVALUATE
           END-PERFORM.
