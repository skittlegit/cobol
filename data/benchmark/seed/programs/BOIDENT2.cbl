       IDENTIFICATION DIVISION.
       PROGRAM-ID. BOIDENT2.
      *----------------------------------------------------------------
      * BENEFICIAL OWNER IDENTIFICATION - PARTNERSHIP FIRMS
      * OWNERSHIP/ENTITLEMENT ABOVE 10 PER CENT OF CAPITAL OR
      * PROFITS, OR CONTROL THROUGH OTHER MEANS
      *----------------------------------------------------------------
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-PARTNER-REC.
           05  WS-CAPITAL-PCT        PIC 9(3)V99 VALUE ZERO.
           05  WS-PROFIT-PCT         PIC 9(3)V99 VALUE ZERO.
           05  WS-CONTROL-IND        PIC X(1) VALUE 'N'.
       01  WS-FLAGS.
           05  WS-IS-BO              PIC X(1) VALUE 'N'.
       01  WS-CONSTANTS.
           05  WS-BO-THRESHOLD       PIC 9(3)V99 VALUE 10.00.
       01  WS-RPT-HEADING            PIC X(36)
           VALUE 'BENEFICIAL OWNER IDENTIFICATION'.
       01  WS-PAGE-NBR               PIC 9(4) VALUE ZERO.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-CAPITAL-PCT
           ACCEPT WS-PROFIT-PCT
           ACCEPT WS-CONTROL-IND
           PERFORM 2000-IDENTIFY-BO
           DISPLAY 'BO: ' WS-IS-BO
           STOP RUN.
       2000-IDENTIFY-BO.
           IF WS-CAPITAL-PCT > WS-BO-THRESHOLD
              OR WS-PROFIT-PCT > WS-BO-THRESHOLD
              OR WS-CONTROL-IND = 'Y'
              MOVE 'Y' TO WS-IS-BO
           END-IF.
