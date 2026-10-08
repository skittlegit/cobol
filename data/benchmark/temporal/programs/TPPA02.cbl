       IDENTIFICATION DIVISION.
       PROGRAM-ID. TPPA02.
      * FIRM ONBOARDING - CALLS THE PARTNER SCREEN PER PARTNER
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-PARTNERS.
           05  WS-PARTNER OCCURS 4 TIMES.
               10  WS-PARTNER-PCT   PIC 9(3)V99.
               10  WS-PARTNER-CTRL  PIC X.
       01  WS-IX                     PIC 9 VALUE ZERO.
       01  WS-FLAG                   PIC X VALUE 'N'.
       01  WS-BO-COUNT               PIC 9 VALUE ZERO.
       PROCEDURE DIVISION.
       1000-MAIN.
           PERFORM VARYING WS-IX FROM 1 BY 1 UNTIL WS-IX > 4
              ACCEPT WS-PARTNER-PCT (WS-IX)
              ACCEPT WS-PARTNER-CTRL (WS-IX)
              CALL 'TPPA02S' USING WS-PARTNER-PCT (WS-IX)
                                   WS-PARTNER-CTRL (WS-IX) WS-FLAG
              IF WS-FLAG = 'Y'
                 ADD 1 TO WS-BO-COUNT
              END-IF
           END-PERFORM
           DISPLAY 'BO COUNT: ' WS-BO-COUNT
           STOP RUN.
