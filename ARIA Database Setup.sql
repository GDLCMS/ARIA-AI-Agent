-- ============================================
-- ARIA DATABASE SETUP
-- Automated Reply & Inbox Agent
-- ============================================

CREATE DATABASE ARIA_DB;
GO

USE ARIA_DB;
GO

-- ─────────────────────────────────────────
-- MAIN EMAIL TABLE
-- ─────────────────────────────────────────
CREATE TABLE ARIA_Emails (
    EmailID         INT IDENTITY(1,1) PRIMARY KEY,
    ThreadID        NVARCHAR(255)   NOT NULL,
    Sender          NVARCHAR(255)   NOT NULL,
    Subject         NVARCHAR(500)   NOT NULL,
    BodyPreview     NVARCHAR(MAX)   NULL,
    ReceivedAt      DATETIME        NOT NULL,
    ProcessedAt     DATETIME        DEFAULT GETDATE(),

    -- AI Output Fields
    Category        NVARCHAR(50)    NOT NULL,
    Urgency         TINYINT         NOT NULL CHECK (Urgency BETWEEN 1 AND 5),
    Summary         NVARCHAR(1000)  NULL,
    SuggestedAction NVARCHAR(50)    NOT NULL,
    DelegateTo      NVARCHAR(255)   NULL,
    DraftReply      NVARCHAR(MAX)   NULL,
    FollowUpDate    DATE            NULL,
    KeyEntities     NVARCHAR(500)   NULL,
    RequiresGabriela BIT            DEFAULT 0,

    -- Workflow
    Status          NVARCHAR(20)    DEFAULT 'PENDING',
    StatusUpdatedAt DATETIME        NULL,
    Notes           NVARCHAR(500)   NULL,

    CONSTRAINT chk_category CHECK (Category IN (
        'VENDOR_SECURITY','TEAM_MANAGEMENT','ESCALATION',
        'MEETING_REQUEST','FYI_ONLY','NEWSLETTER',
        'ADMIN','LEGAL','PROCUREMENT','FOLLOW_UP_NEEDED','SPAM'
    )),
    CONSTRAINT chk_action CHECK (SuggestedAction IN (
        'REPLY_NOW','DELEGATE','ARCHIVE','SCHEDULE','FOLLOW_UP','DELETE'
    )),
    CONSTRAINT chk_status CHECK (Status IN (
        'PENDING','APPROVED','SENT','ARCHIVED','DELEGATED'
    ))
);
GO

-- ─────────────────────────────────────────
-- FOLLOW-UP TRACKER TABLE
-- ─────────────────────────────────────────
CREATE TABLE ARIA_FollowUps (
    FollowUpID      INT IDENTITY(1,1) PRIMARY KEY,
    EmailID         INT             NOT NULL FOREIGN KEY 
                                    REFERENCES ARIA_Emails(EmailID),
    FollowUpDate    DATE            NOT NULL,
    ReminderSent    BIT             DEFAULT 0,
    Resolved        BIT             DEFAULT 0,
    ResolvedAt      DATETIME        NULL,
    Notes           NVARCHAR(500)   NULL
);
GO

-- ─────────────────────────────────────────
-- AUDIT LOG TABLE
-- ─────────────────────────────────────────
CREATE TABLE ARIA_AuditLog (
    LogID           INT IDENTITY(1,1) PRIMARY KEY,
    EmailID         INT             NOT NULL,
    Action          NVARCHAR(50)    NOT NULL,
    PerformedAt     DATETIME        DEFAULT GETDATE(),
    OldStatus       NVARCHAR(20)    NULL,
    NewStatus       NVARCHAR(20)    NULL,
    Notes           NVARCHAR(500)   NULL
);
GO

-- ─────────────────────────────────────────
-- USEFUL VIEWS
-- ─────────────────────────────────────────

-- Daily dashboard view
CREATE VIEW vw_ARIA_Dashboard AS
SELECT 
    EmailID,
    Sender,
    Subject,
    ReceivedAt,
    Category,
    Urgency,
    Summary,
    SuggestedAction,
    DelegateTo,
    DraftReply,
    FollowUpDate,
    KeyEntities,
    RequiresGabriela,
    Status,
    Notes,
    CASE Urgency
        WHEN 5 THEN '🔴 Critical'
        WHEN 4 THEN '🟠 High'
        WHEN 3 THEN '🟡 Medium'
        WHEN 2 THEN '🔵 Low'
        WHEN 1 THEN '⚪ Informational'
    END AS UrgencyLabel
FROM ARIA_Emails
WHERE CAST(ReceivedAt AS DATE) = CAST(GETDATE() AS DATE);
GO

-- Pending follow-ups view
CREATE VIEW vw_ARIA_FollowUps AS
SELECT 
    e.EmailID,
    e.Sender,
    e.Subject,
    e.Summary,
    f.FollowUpDate,
    DATEDIFF(DAY, GETDATE(), f.FollowUpDate) AS DaysUntilDue,
    f.Resolved
FROM ARIA_Emails e
JOIN ARIA_FollowUps f ON e.EmailID = f.EmailID
WHERE f.Resolved = 0
ORDER BY f.FollowUpDate ASC;
GO

-- ─────────────────────────────────────────
-- STORED PROCEDURES
-- ─────────────────────────────────────────

-- Insert new email from Power Automate
CREATE PROCEDURE sp_ARIA_InsertEmail
    @ThreadID        NVARCHAR(255),
    @Sender          NVARCHAR(255),
    @Subject         NVARCHAR(500),
    @BodyPreview     NVARCHAR(MAX),
    @ReceivedAt      DATETIME,
    @Category        NVARCHAR(50),
    @Urgency         TINYINT,
    @Summary         NVARCHAR(1000),
    @SuggestedAction NVARCHAR(50),
    @DelegateTo      NVARCHAR(255),
    @DraftReply      NVARCHAR(MAX),
    @FollowUpDate    DATE,
    @KeyEntities     NVARCHAR(500),
    @RequiresGabriela BIT
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO ARIA_Emails (
        ThreadID, Sender, Subject, BodyPreview, ReceivedAt,
        Category, Urgency, Summary, SuggestedAction,
        DelegateTo, DraftReply, FollowUpDate, KeyEntities, RequiresGabriela
    )
    VALUES (
        @ThreadID, @Sender, @Subject, @BodyPreview, @ReceivedAt,
        @Category, @Urgency, @Summary, @SuggestedAction,
        @DelegateTo, @DraftReply, @FollowUpDate, @KeyEntities, @RequiresGabriela
    );

    -- Auto-create follow-up entry if needed
    IF @FollowUpDate IS NOT NULL
    BEGIN
        INSERT INTO ARIA_FollowUps (EmailID, FollowUpDate)
        VALUES (SCOPE_IDENTITY(), @FollowUpDate);
    END
END;
GO

-- Update email status (called from Streamlit)
CREATE PROCEDURE sp_ARIA_UpdateStatus
    @EmailID    INT,
    @NewStatus  NVARCHAR(20),
    @Notes      NVARCHAR(500) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @OldStatus NVARCHAR(20);
    SELECT @OldStatus = Status FROM ARIA_Emails WHERE EmailID = @EmailID;

    UPDATE ARIA_Emails 
    SET Status = @NewStatus,
        StatusUpdatedAt = GETDATE(),
        Notes = ISNULL(@Notes, Notes)
    WHERE EmailID = @EmailID;

    INSERT INTO ARIA_AuditLog (EmailID, Action, OldStatus, NewStatus)
    VALUES (@EmailID, 'STATUS_CHANGE', @OldStatus, @NewStatus);
END;
GO

PRINT '✅ ARIA_DB created successfully. Ready for Checkpoint 2.';