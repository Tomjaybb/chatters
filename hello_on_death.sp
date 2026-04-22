#include <sourcemod>

#pragma semicolon 1
#pragma newdecls required

public Plugin myinfo =
{
    name = "Hello On Death",
    author = "chatters",
    description = "Prints hello world in chat whenever a player dies",
    version = "1.0.0",
    url = ""
};

public void OnPluginStart()
{
    HookEvent("player_death", Event_PlayerDeath, EventHookMode_Post);
}

public Action Event_PlayerDeath(Event event, const char[] name, bool dontBroadcast)
{
    PrintToChatAll("hello world");
    return Plugin_Continue;
}
