       IDENTIFICATION DIVISION.
       PROGRAM-ID. CLOSPEN6.
      * CLOSURE REQUEST BATCH - SLA CHECK OVER A REQUEST TABLE
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-REQ-COUNT              PIC 9(2) VALUE ZERO.
       01  WS-REQ-TABLE.
           05  WS-REQ-DAYS OCCURS 10 PIC 9(4).
       01  WS-IDX                    PIC 9(2) VALUE 1.
       01  WS-TOT-PENALTY            PIC 9(9)V99 VALUE ZERO.
       01  WS-RPT-HEADING            PIC X(2)
           VALUE SPACES.
       01  FILLER                    PIC X(30) VALUE SPACES.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-REQ-COUNT
           PERFORM VARYING WS-IDX FROM 1 BY 1
                   UNTIL WS-IDX > WS-REQ-COUNT
              ACCEPT WS-REQ-DAYS (WS-IDX)
              PERFORM 2000-ONE-REQ
           END-PERFORM
           DISPLAY 'TOTAL: ' WS-TOT-PENALTY
           STOP RUN.
       2000-ONE-REQ.
           IF WS-REQ-DAYS (WS-IDX) > 7
              COMPUTE WS-TOT-PENALTY = WS-TOT-PENALTY
                      + 500 * (WS-REQ-DAYS (WS-IDX) - 7)
           END-IF.
