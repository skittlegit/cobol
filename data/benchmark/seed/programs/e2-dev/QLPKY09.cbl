       IDENTIFICATION DIVISION.
       PROGRAM-ID. QLPKY09.
      * PERIODIC KYC UPDATION DUE YEAR BY RISK
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-RISK                   PIC X(1) VALUE 'L'.
       01  WS-LAST-KYC-YEAR          PIC 9(4) VALUE ZERO.
       01  WS-DUE-YEAR               PIC 9(4) VALUE ZERO.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-RISK
           ACCEPT WS-LAST-KYC-YEAR
           PERFORM 2000-DUE
           DISPLAY 'DUE: ' WS-DUE-YEAR
           STOP RUN.
       2000-DUE.
           EVALUATE WS-RISK
              WHEN 'H'
                 COMPUTE WS-DUE-YEAR = WS-LAST-KYC-YEAR + 2
              WHEN 'M'
                 COMPUTE WS-DUE-YEAR = WS-LAST-KYC-YEAR + 8
              WHEN OTHER
                 COMPUTE WS-DUE-YEAR = WS-LAST-KYC-YEAR + 10
           END-EVALUATE.
