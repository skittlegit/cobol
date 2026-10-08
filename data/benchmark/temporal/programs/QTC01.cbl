       IDENTIFICATION DIVISION.
       PROGRAM-ID. QTC01.
      * COMPANY OWNERS - HOLDING TABLE BY INTEREST TYPE
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-HOLDINGS.
           05  WS-HOLDING OCCURS 3 TIMES.
               10  WS-HOLD-TYPE     PIC X(1).
               10  WS-HOLD-PCT      PIC 9(3)V99.
       01  WS-OTHER-CONTROL          PIC X(1) VALUE 'N'.
       01  WS-IX                     PIC 9 VALUE ZERO.
       01  WS-IS-BO                  PIC X(1) VALUE 'N'.
       PROCEDURE DIVISION.
       1000-MAIN.
      * ONE ROW EACH FOR SHARES (S), CAPITAL (C) AND PROFITS (P).
           PERFORM VARYING WS-IX FROM 1 BY 1 UNTIL WS-IX > 3
              ACCEPT WS-HOLD-TYPE (WS-IX)
              ACCEPT WS-HOLD-PCT (WS-IX)
           END-PERFORM
           ACCEPT WS-OTHER-CONTROL
           PERFORM 2000-SCAN
           DISPLAY 'BO: ' WS-IS-BO
           STOP RUN.
       2000-SCAN.
           MOVE WS-OTHER-CONTROL TO WS-IS-BO
           PERFORM VARYING WS-IX FROM 1 BY 1 UNTIL WS-IX > 3
              IF WS-HOLD-PCT (WS-IX) > 25
                 MOVE 'Y' TO WS-IS-BO
              END-IF
           END-PERFORM.
