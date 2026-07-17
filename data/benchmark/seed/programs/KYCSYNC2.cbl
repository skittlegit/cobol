       IDENTIFICATION DIVISION.
       PROGRAM-ID. KYCSYNC2.
      *----------------------------------------------------------------
      * CKYCR RECORD SYNC - UPLOAD WITHIN SEVEN DAYS OF RECEIVING
      * UPDATED KYC INFORMATION FROM CUSTOMER
      *----------------------------------------------------------------
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-CUST-REC.
           05  WS-CUST-ID            PIC X(10) VALUE SPACES.
           05  WS-DAYS-SINCE-UPD     PIC 9(4) VALUE ZERO.
       01  WS-FLAGS.
           05  WS-SLA-STATUS         PIC X(8) VALUE SPACES.
       01  WS-RPT-HEADING            PIC X(36)
           VALUE 'CKYCR SYNCRONISATION REGISTER'.
       01  WS-PRINT-AREA.
           05  WS-PRINT-LINE OCCURS 66 PIC X(72).
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-CUST-ID
           ACCEPT WS-DAYS-SINCE-UPD
           PERFORM 2000-CHECK-SLA
           DISPLAY 'SLA: ' WS-SLA-STATUS
           STOP RUN.
       2000-CHECK-SLA.
           IF WS-DAYS-SINCE-UPD > 7
              MOVE 'OVERDUE' TO WS-SLA-STATUS
           ELSE
              MOVE 'INSLA' TO WS-SLA-STATUS
           END-IF.
