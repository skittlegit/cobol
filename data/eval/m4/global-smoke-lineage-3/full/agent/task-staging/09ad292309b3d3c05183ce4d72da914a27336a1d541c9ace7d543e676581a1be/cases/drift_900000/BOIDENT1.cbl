       IDENTIFICATION DIVISION.
       PROGRAM-ID. BOIDENT1.
      *----------------------------------------------------------------
      * BENEFICIAL OWNER IDENTIFICATION - PARTNERSHIP FIRMS
      * REF: KYC MD 2016 SEC 3(A)(IV)(B) - NATURAL PERSON WITH
      * OWNERSHIP/ENTITLEMENT OF MORE THAN 15 PER CENT OF CAPITAL
      * OR PROFITS OF THE PARTNERSHIP
      *----------------------------------------------------------------
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-PARTNER-REC.
           05  WS-CAPITAL-PCT        PIC 9(3)V99 VALUE ZERO.
           05  WS-PROFIT-PCT         PIC 9(3)V99 VALUE ZERO.
       01  WS-FLAGS.
           05  WS-IS-BO              PIC X(1) VALUE 'N'.
       01  WS-CONSTANTS.
           05  WS-BO-THRESHOLD       PIC 9(3)V99 VALUE 15.00.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-CAPITAL-PCT
           ACCEPT WS-PROFIT-PCT
           PERFORM 2000-IDENTIFY-BO
           DISPLAY 'BO: ' WS-IS-BO
           STOP RUN.
       2000-IDENTIFY-BO.
           IF WS-CAPITAL-PCT > WS-BO-THRESHOLD
              OR WS-PROFIT-PCT > WS-BO-THRESHOLD
              MOVE 'Y' TO WS-IS-BO
           END-IF.
