       IDENTIFICATION DIVISION.
       PROGRAM-ID. KYCSYNC1.
      *----------------------------------------------------------------
      * CKYCR RECORD SYNC - QUEUES UPDATED KYC DATA FOR UPLOAD
      * REF: KYC MD 2016 PARA 56 - FILE ELECTRONICALLY TO CKYCR
      *----------------------------------------------------------------
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-CUST-REC.
           05  WS-CUST-ID            PIC X(10) VALUE SPACES.
           05  WS-UPD-RECEIVED       PIC X(1) VALUE 'N'.
       01  WS-QUEUE-AREAS.
           05  WS-QUEUE-STATUS       PIC X(8) VALUE SPACES.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-CUST-ID
           ACCEPT WS-UPD-RECEIVED
           PERFORM 2000-QUEUE-UPLOAD
           DISPLAY 'QUEUE: ' WS-QUEUE-STATUS
           STOP RUN.
       2000-QUEUE-UPLOAD.
           IF WS-UPD-RECEIVED = 'Y'
              MOVE 'QUEUED' TO WS-QUEUE-STATUS
           ELSE
              MOVE 'NOCHANGE' TO WS-QUEUE-STATUS
           END-IF.
