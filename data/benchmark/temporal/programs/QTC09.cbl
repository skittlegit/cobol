       IDENTIFICATION DIVISION.
       PROGRAM-ID. QTC09.
      * SHAREHOLDER FILE - COUNT BENEFICIAL OWNERS
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-OWNERS.
           05  WS-OWNER OCCURS 4 TIMES.
               10  WS-O-SHARES      PIC 9(3)V99.
               10  WS-O-CAPITAL     PIC 9(3)V99.
               10  WS-O-PROFITS     PIC 9(3)V99.
               10  WS-O-CONTROL     PIC X(1).
       01  WS-IX                     PIC 9 VALUE ZERO.
       01  WS-BO-COUNT               PIC 9 VALUE ZERO.
       PROCEDURE DIVISION.
       1000-MAIN.
           PERFORM VARYING WS-IX FROM 1 BY 1 UNTIL WS-IX > 4
              ACCEPT WS-O-SHARES (WS-IX)
              ACCEPT WS-O-CAPITAL (WS-IX)
              ACCEPT WS-O-PROFITS (WS-IX)
              ACCEPT WS-O-CONTROL (WS-IX)
           END-PERFORM
           PERFORM 2000-COUNT
           DISPLAY 'BO COUNT: ' WS-BO-COUNT
           STOP RUN.
       2000-COUNT.
           MOVE ZERO TO WS-BO-COUNT
           PERFORM VARYING WS-IX FROM 1 BY 1 UNTIL WS-IX > 4
              IF WS-O-SHARES (WS-IX) > 25
                 OR WS-O-CAPITAL (WS-IX) > 25
                 OR WS-O-PROFITS (WS-IX) > 25
                 OR WS-O-CONTROL (WS-IX) = 'Y'
                 ADD 1 TO WS-BO-COUNT
              END-IF
           END-PERFORM.
