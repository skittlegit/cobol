       IDENTIFICATION DIVISION.
       PROGRAM-ID. XQNEK06.
      * NORTH-EAST REGION - BUREAU SYNC RUN CONTROL
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
      * RUN CONTROL AND HOUSEKEEPING
       01  WS-RUN-STAMP.
           05  WS-RUN-YYYY           PIC 9(4).
           05  WS-RUN-MM             PIC 9(2).
           05  WS-RUN-DD             PIC 9(2).
           05  WS-RUN-REST           PIC X(13).
       01  WS-RUN-OK                 PIC X(1) VALUE 'Y'.
       01  WS-BRANCH-TABLE.
           05  WS-BRANCH-CODE   PIC X(4) OCCURS 9 TIMES.
       01  WS-BX                     PIC 9(2) VALUE ZERO.
       01  WS-CUST-NAME              PIC X(30) VALUE SPACES.
       01  WS-ACCT-STATUS            PIC X(1) VALUE 'A'.
       01  WS-STATUS-TEXT            PIC X(12) VALUE SPACES.
       01  WS-ACCT-AGE-MONTHS        PIC 9(4) VALUE ZERO.
       01  WS-AGE-BUCKET             PIC X(6) VALUE SPACES.
       01  WS-AMT-WORK               PIC 9(9)V99 VALUE ZERO.
       01  WS-AMT-EDIT               PIC ZZZ,ZZZ,ZZ9.99.
       01  WS-AUDIT-KEY              PIC X(40) VALUE SPACES.
       01  WS-ACCT-NUMBER            PIC 9(11) VALUE ZERO.
       01  WS-CHECK-SUM              PIC 9(4) VALUE ZERO.
       01  WS-DIGIT-IX               PIC 9(2) VALUE ZERO.
       01  WS-DIGIT                  PIC 9 VALUE ZERO.
       01  WS-LINE-COUNT             PIC 9(3) VALUE ZERO.
       01  WS-PAGE-COUNT             PIC 9(3) VALUE ZERO.
       01  WS-RECORDS-SEEN           PIC 9(7) VALUE ZERO.
       01  WS-ERRORS-SEEN            PIC 9(5) VALUE ZERO.
       01  WS-HEADER-LINE.
           05  WS-HDR-TITLE          PIC X(40) VALUE SPACES.
           05  WS-HDR-PAGE           PIC ZZ9.
       01  WS-AUDIT-REC.
           05  WS-AUD-KEY            PIC X(40).
           05  WS-AUD-STATUS         PIC X(12).
           05  WS-AUD-BUCKET         PIC X(6).
      * STATEMENT AND REWARDS WORK AREAS
       01  WS-LEAP-YEAR              PIC X(1) VALUE 'N'.
       01  WS-YEAR-REM-4             PIC 9 VALUE ZERO.
       01  WS-YEAR-REM-100           PIC 9(2) VALUE ZERO.
       01  WS-YEAR-REM-400           PIC 9(3) VALUE ZERO.
       01  WS-BRANCH-WANTED          PIC X(4) VALUE 'BLR1'.
       01  WS-BRANCH-FOUND           PIC X(1) VALUE 'N'.
       01  WS-SPEND-AMT              PIC 9(9)V99 VALUE ZERO.
       01  WS-REWARD-POINTS          PIC 9(7) VALUE ZERO.
       01  WS-ADDR-LINE-1            PIC X(30) VALUE SPACES.
       01  WS-ADDR-LINE-2            PIC X(30) VALUE SPACES.
       01  WS-ADDR-PRINT             PIC X(64) VALUE SPACES.
       01  WS-FX-AMOUNT              PIC 9(9)V9(4) VALUE ZERO.
       01  WS-FX-ROUNDED             PIC 9(9)V99 VALUE ZERO.
       01  WS-STMT-MESSAGE           PIC X(40) VALUE SPACES.
       01  WS-UTIL-PCT               PIC 9(3)V99 VALUE ZERO.
       01  WS-UTIL-BAND              PIC X(6) VALUE SPACES.
       01  WS-SANCTIONED-LMT         PIC 9(9)V99 VALUE 1.
       01  WS-CURRENT-BAL            PIC 9(9)V99 VALUE ZERO.
       LINKAGE SECTION.
       01  LK-REGION-CODE            PIC X(1).
       COPY XQNEF06.
       PROCEDURE DIVISION USING LK-REGION-CODE WS-XQNE-CIC-CTL.
       1000-SET-RUN.
           PERFORM 0100-INITIALISE
           PERFORM 0150-CHECK-RUN-DATE
           PERFORM 0200-LOAD-BRANCHES
           PERFORM 0160-LEAP-YEAR
           MOVE 'N' TO WS-XQNE-CIC-RUN
           IF LK-REGION-CODE = 'X'
              MOVE 'Y' TO WS-XQNE-CIC-RUN
           END-IF
           PERFORM 0600-WRITE-AUDIT
           PERFORM 0900-RUN-STATISTICS
           GOBACK.
       0100-INITIALISE.
           MOVE ZERO TO WS-LINE-COUNT WS-PAGE-COUNT
           MOVE ZERO TO WS-RECORDS-SEEN WS-ERRORS-SEEN
           MOVE FUNCTION CURRENT-DATE TO WS-RUN-STAMP
           MOVE 'ACCOUNT CONTROL REPORT' TO WS-HDR-TITLE.
       0150-CHECK-RUN-DATE.
           MOVE 'Y' TO WS-RUN-OK
           IF WS-RUN-YYYY < 1990 OR WS-RUN-YYYY > 2099
              MOVE 'N' TO WS-RUN-OK
              ADD 1 TO WS-ERRORS-SEEN
           END-IF
           IF WS-RUN-MM < 1 OR WS-RUN-MM > 12
              MOVE 'N' TO WS-RUN-OK
           END-IF.
       0200-LOAD-BRANCHES.
           MOVE 'MUM1' TO WS-BRANCH-CODE (1)
           MOVE 'DEL1' TO WS-BRANCH-CODE (2)
           MOVE 'BLR1' TO WS-BRANCH-CODE (3)
           MOVE 'CHN1' TO WS-BRANCH-CODE (4)
           MOVE 'HYD1' TO WS-BRANCH-CODE (5)
           MOVE 'KOL1' TO WS-BRANCH-CODE (6)
           MOVE 'PUN1' TO WS-BRANCH-CODE (7)
           MOVE 'AHM1' TO WS-BRANCH-CODE (8)
           MOVE 'JAI1' TO WS-BRANCH-CODE (9).
       0160-LEAP-YEAR.
           DIVIDE WS-RUN-YYYY BY 4 GIVING WS-DIGIT
                  REMAINDER WS-YEAR-REM-4
           DIVIDE WS-RUN-YYYY BY 100 GIVING WS-DIGIT
                  REMAINDER WS-YEAR-REM-100
           DIVIDE WS-RUN-YYYY BY 400 GIVING WS-DIGIT
                  REMAINDER WS-YEAR-REM-400
           MOVE 'N' TO WS-LEAP-YEAR
           IF WS-YEAR-REM-4 = ZERO AND WS-YEAR-REM-100 NOT = ZERO
              MOVE 'Y' TO WS-LEAP-YEAR
           END-IF
           IF WS-YEAR-REM-400 = ZERO
              MOVE 'Y' TO WS-LEAP-YEAR
           END-IF.
       0600-WRITE-AUDIT.
           MOVE WS-AUDIT-KEY TO WS-AUD-KEY
           MOVE WS-STATUS-TEXT TO WS-AUD-STATUS
           MOVE WS-AGE-BUCKET TO WS-AUD-BUCKET
           ADD 1 TO WS-RECORDS-SEEN.
       0900-RUN-STATISTICS.
           IF WS-ERRORS-SEEN > ZERO
              MOVE 'N' TO WS-RUN-OK
           END-IF
           ADD WS-RECORDS-SEEN TO WS-PAGE-COUNT.
