       IDENTIFICATION DIVISION.
       PROGRAM-ID. KYCPR9.
      * PERIODIC KYC REFRESH SCHEDULER BY RISK BAND
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-RISK-BAND              PIC X(1) VALUE SPACE.
       01  WS-LAST-YYYY              PIC 9(4) VALUE ZERO.
       01  WS-NEXT-YYYY              PIC 9(4) VALUE ZERO.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-RISK-BAND
           ACCEPT WS-LAST-YYYY
           PERFORM 2000-SCHEDULE
           DISPLAY 'NEXT: ' WS-NEXT-YYYY
           STOP RUN.
       2000-SCHEDULE.
           IF WS-RISK-BAND = 'H'
              COMPUTE WS-NEXT-YYYY = WS-LAST-YYYY + 2
           ELSE
              IF WS-RISK-BAND = 'M'
                 COMPUTE WS-NEXT-YYYY = WS-LAST-YYYY + 8
              ELSE
                 COMPUTE WS-NEXT-YYYY = WS-LAST-YYYY + 10
              END-IF
           END-IF.
