-- mod_muc_jwt_owner: JWT context.user.moderator=true 的参会者授予 MUC owner（主持人）角色
--
-- 背景：JWT_ALLOW_EMPTY=1 部署下，所有连接都在主域匿名会话，prosody 不会把
-- JWT 的 moderator 声明映射成 MUC 角色；jicofo 的 enable-auto-owner（默认开）
-- 会把第一个进会者自动提升为 owner，造成"人人都是主持人"。
-- 本模块 + ENABLE_AUTO_OWNER=false 恢复"仅 JWT 声明的 moderator 才是主持人"。
--
-- 机制（与官方 mod_muc_allowners 同款）：pre-join 打标 → joined 时 set_affiliation

-- A pending claim belongs to one room attempt, not every room using a bare JID.
-- Keep it local to this module generation so reloads cannot restore old claims.
local joining_owners = setmetatable({}, { __mode = "k" });
local transfer_gate = module:shared("/" .. module.host .. "/muc_host_transfer/gate");
-- Optional online revocation gate. Configure both values together; absence keeps
-- the existing deployment behavior. Never enable transfer without this gate.
local role_check_url = module:get_option_string("host_role_check_url");
local role_check_secret = module:get_option_string("host_role_check_secret");
local http, json, st, muc;
if role_check_url then
    assert(role_check_url:match("^https?://"), "invalid host role check URL");
    assert(role_check_secret and #role_check_secret >= 32, "host role check secret required");
    http = require "net.http";
    json = require "util.json";
    st = require "util.stanza";
    muc = module:depends("muc");
end

-- Prosody 13 normalizes internal set_affiliation(true, ...) to actor=nil before
-- muc-pre-set-affiliation; client MUC admin IQs carry the sender JID as actor.
-- Do not grant permission here: leave every other operation to Prosody checks.
module:hook("muc-pre-set-affiliation", function(event)
    if event.actor and (event.affiliation == "owner" or event.affiliation == "admin") then
        event.allowed = false;
        event.error = { type = "cancel", condition = "not-allowed" };
    end
end, -100);

-- Role changes can grant moderator without changing affiliation. Block that
-- separate path too; kick/demotion continue through core authorization.
module:hook("muc-pre-set-role", function(event)
    if event.actor and event.role == "moderator" then
        event.allowed = false;
        event.error = "cancel";
        event.condition = "not-allowed";
    end
end, -100);

local function claim_is_moderator(session)
    local user = session and session.jitsi_meet_context_user;
    if not user then
        return false;
    end
    return user.moderator == true or user.moderator == "true";
end

module:hook("muc-occupant-pre-join", function(event)
    local session = event.origin;
    local occupant = event.occupant;
    local room = event.room;
    if not room or not occupant or not occupant.bare_jid then return; end
    -- Core component administrators (e.g. authenticated Jicofo) have immutable
    -- automatic ownership, not transferable business-host authority. Ask the
    -- same MUC permission provider as core; never infer trust from a nickname,
    -- client JWT claim or an unbound stanza from attribute.
    local source = event.stanza and event.stanza.attr.from;
    if muc and source and session and session.full_jid == source
        and muc.module:could(":automatic-ownership", source) then return; end
    if role_check_url and room:get_affiliation(occupant.bare_jid) == "owner" then
        -- Prosody creates the occupant with the saved affiliation's role before
        -- this hook. Revoke it before the occupant is saved or publicised; the
        -- asynchronous check in joined may restore owner afterwards.
        local gate = transfer_gate[room];
        local existing = false;
        for _, current in room:each_occupant() do
            if current.bare_jid == occupant.bare_jid then existing = true; break; end
        end
        if not existing and not (gate and (gate.busy or gate.blocked)) then
            local ok, changed = pcall(room.set_affiliation, room, true, occupant.bare_jid, "none", "host-role-recheck");
            if ok and changed == true then
                occupant.role = room:get_default_role("none");
            else
                existing = true;
            end
        else
            existing = true;
        end
        if existing then
            session.send(st.error_reply(event.stanza, "cancel", "conflict", nil, room.jid));
            return true;
        end
    end
    local pending = joining_owners[room];
    if not pending then
        pending = setmetatable({}, { __mode = "k" });
        joining_owners[room] = pending;
    end
    -- Always overwrite: an anonymous retry must revoke a previous pending claim.
    pending[occupant] = session and claim_is_moderator(session)
        and { bare = occupant.bare_jid, origin = session } or nil;
end, 3);

-- The product rebuilds its iframe after confirmation to use the rotated JWT.
-- Anonymous authentication then uses a new bare JID. Do not leave the departed
-- session's affiliation blocking that freshly online-verified identity.
module:hook("muc-occupant-left", function(event)
    if not role_check_url then return; end
    local room, occupant = event.room, event.occupant;
    if not room or not occupant or not occupant.bare_jid then return; end
    local bare = occupant.bare_jid;
    if muc.module:could(":automatic-ownership", bare) then return; end
    local gate = transfer_gate[room];
    if gate and (gate.busy or gate.blocked or gate.inflight or gate.awaiting_ack) then return; end
    for _, current in room:each_occupant() do
        if current.bare_jid == bare then return; end
    end
    if room:get_affiliation(bare) == "owner" then
        local ok, changed = pcall(room.set_affiliation, room, true, bare, "none", "host-session-left");
        if not ok or changed ~= true then
            module:log("warn", "Departed host affiliation cleanup failed; retaining fail-closed authority");
        end
    end
end, 2);

module:hook("muc-occupant-joined", function(event)
    local room, occupant = event.room, event.occupant;
    if not room or not occupant then
        return;
    end
    local bare = occupant.bare_jid;
    local pending = joining_owners[room];
    local claim = pending and pending[occupant];
    if pending then pending[occupant] = nil; end
    if claim and claim.bare == bare and claim.origin == event.origin
        and claim_is_moderator(event.origin) then
        if not role_check_url then
            room:set_affiliation(true, bare, "owner");
            return;
        end
        local identity = event.origin.jitsi_meet_context_user.id;
        local room_name = room.jid:match("^(%d%d%d%d%d%d%d%d%d)@");
        if type(identity) ~= "string" or #identity ~= 51 or not room_name then
            module:log("warn", "Host role check skipped: invalid identity shape or room"); return;
        end
        local nick = occupant.nick;
        local epoch = transfer_gate[room] and transfer_gate[room].epoch or 0;
        local retries = 0;
        local function check()
        local active_gate = transfer_gate[room];
        if active_gate and (active_gate.busy or active_gate.blocked or active_gate.epoch ~= epoch) then return; end
        local member = room:get_occupant_by_nick(nick);
        if not member or member.bare_jid ~= bare then return; end
        local completed = false;
        http.request(role_check_url, { method = "POST", body = json.encode({roomName=room_name, identity=identity}),
            headers = { ["Content-Type"] = "application/json", ["X-Role-Check-Secret"] = role_check_secret } },
            function(body, code)
                if completed then return; end
                completed = true;
                -- Request completion is not authority: recheck current occupant,
                -- origin and claim after the asynchronous trust-boundary crossing.
                if code ~= 200 or body ~= "true" then
                    module:log("warn", "Host role check denied or unavailable (HTTP %s)", tostring(code)); return;
                end
                local gate = transfer_gate[room];
                if gate and (gate.busy or gate.blocked or gate.epoch ~= epoch) then return; end
                local current = room:get_occupant_by_nick(nick);
                if not current or current.bare_jid ~= bare then return; end
                local source = event.stanza and event.stanza.attr.from;
                local connected = source and room:get_occupant_by_real_jid(source);
                if not connected or connected.nick ~= nick or connected.bare_jid ~= bare then return; end
                if not claim_is_moderator(event.origin) or event.origin.jitsi_meet_context_user.id ~= identity then return; end
                for owner in room:each_affiliation("owner") do
                    if owner ~= bare and not muc.module:could(":automatic-ownership", owner) then
                        local online = false;
                        for _, member in room:each_occupant() do
                            if member.bare_jid == owner then online = true; break; end
                        end
                        module:log("warn", "Host role grant blocked by another stored owner (room=%s, online=%s)", room_name, tostring(online));
                        -- Iframe disposal can lag behind its replacement join.
                        -- Never revoke a live owner here. Retry the online API
                        -- check after departure, with the same epoch/session guards.
                        if online and retries < 15 then
                            retries = retries + 1;
                            module:add_timer(2, check);
                        end
                        return;
                    end
                end
                room:set_affiliation(true, bare, "owner");
            end);
        end
        check();
    end
end, 2);
