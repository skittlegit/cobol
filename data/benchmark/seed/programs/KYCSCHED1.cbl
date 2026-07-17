       IDENTIFICATION DIVISION.
       PROGRAM-ID. KYCSCHED1.
      *----------------------------------------------------------------
      * PERIODIC KYC UPDATION SCHEDULER
      * HIGH RISK 2 YRS / MEDIUM 8 YRS / LOW 10 YRS
      *----------------------------------------------------------------
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-CUST-REC.
           05  WS-RISK-RATING        PIC X(1) VALUE SPACE.
           05  WS-YEARS-SINCE-KYC    PIC 9(2) VALUE ZERO.
       01  WS-FLAGS.
           05  WS-KYC-DUE            PIC X(1) VALUE 'N'.
       01  FILLER                    PIC X(7) VALUE SPACES.
       01  FILLER                    PIC X(7) VALUE SPACES.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-RISK-RATING
           ACCEPT WS-YEARS-SINCE-KYC
           PERFORM 2000-CHECK-DUE
           DISPLAY 'KYC-DUE: ' WS-KYC-DUE
           STOP RUN.
       2000-CHECK-DUE.
           EVALUATE WS-RISK-RATING
             WHEN 'H'
               IF WS-YEARS-SINCE-KYC >= 2
                  MOVE 'Y' TO WS-KYC-DUE
               END-IF
             WHEN 'M'
               IF WS-YEARS-SINCE-KYC >= 8
                  MOVE 'Y' TO WS-KYC-DUE
               END-IF
             WHEN OTHER
               IF WS-YEARS-SINCE-KYC >= 10
                  MOVE 'Y' TO WS-KYC-DUE
               END-IF
           END-EVALUATE.
