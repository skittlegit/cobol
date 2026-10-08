       IDENTIFICATION DIVISION.
       PROGRAM-ID. QTP18.
      * PARTNERSHIP - PARTNER TABLE, COUNT OWNERS
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-PARTNERS.
           05  WS-PARTNER OCCURS 4 TIMES.
               10  WS-P-CAPITAL     PIC 9(3)V99.
               10  WS-P-PROFIT      PIC 9(3)V99.
               10  WS-P-CONTROL     PIC X(1).
       01  WS-IX                     PIC 9 VALUE ZERO.
       01  WS-BO-COUNT               PIC 9 VALUE ZERO.
       PROCEDURE DIVISION.
       1000-MAIN.
           PERFORM VARYING WS-IX FROM 1 BY 1 UNTIL WS-IX > 4
              ACCEPT WS-P-CAPITAL (WS-IX)
              ACCEPT WS-P-PROFIT (WS-IX)
              ACCEPT WS-P-CONTROL (WS-IX)
           END-PERFORM
           PERFORM 2000-COUNT
           DISPLAY 'BO COUNT: ' WS-BO-COUNT
           STOP RUN.
       2000-COUNT.
           MOVE ZERO TO WS-BO-COUNT
           PERFORM VARYING WS-IX FROM 1 BY 1 UNTIL WS-IX > 4
              IF WS-P-CAPITAL (WS-IX) > 15 OR WS-P-PROFIT (WS-IX) > 15
                 OR WS-P-CONTROL (WS-IX) = 'Y'
                 ADD 1 TO WS-BO-COUNT
              END-IF
           END-PERFORM.
