local HttpService = game:GetService("HttpService")
local RunService = game:GetService("RunService")

local Spool = {
	Endpoint = "https://YOUR_API_GATEWAY_URL/events",
	ApiKey = "YOUR_API_GATEWAY_KEY",
	Token = "YOUR_SPOOL_TOKEN",

	Stage = RunService:IsStudio() and "development" or "production",
}

function Spool.Track(eventName, properties)
	local payload = {
		event = eventName,
		stage = Spool.Stage,
		game_id = tostring(game.GameId),
		place_id = tostring(game.PlaceId),
		properties = properties or {},
	}

	local success, response = pcall(function()
		return HttpService:RequestAsync({
			Url = Spool.Endpoint,
			Method = "POST",
			Headers = {
				["Content-Type"] = "application/json",
				["X-API-Key"] = Spool.ApiKey,
				["X-Spool-Token"] = Spool.Token,
			},
			Body = HttpService:JSONEncode(payload),
		})
	end)

	if not success then
		warn("[Spool] Request failed:", response)
		return false
	end

	if not response.Success then
		warn("[Spool] HTTP error:", response.StatusCode, response.Body)
		return false
	end

	return true
end

return Spool
