package main

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"slices"
	"sort"
	"strings"
	"time"
	_ "time/tzdata" // embed the timezone database (Windows has none)

	"github.com/joho/godotenv"
)

var mexicoCity = mustLoadLocation("America/Mexico_City")

func mustLoadLocation(name string) *time.Location {
	// Load the location and fatal if it fails
	loc, err := time.LoadLocation(name)
	if err != nil {
		log.Fatal(err)
	}
	return loc
}

type Match struct {
	ID       int       `json:"id"`
	UTCDate  time.Time `json:"utcDate"`
	Status   string    `json:"status"`
	HomeTeam struct {
		Name string `json:"name"`
	} `json:"homeTeam"`
	AwayTeam struct {
		Name string `json:"name"`
	} `json:"awayTeam"`
	Competition struct {
		Name string `json:"name"`
	} `json:"competition"`
	Score ScoreType `json:"score"`
}

type ScoreType struct {
	Winner   *string `json:"winner"`
	FullTime struct {
		Home *int `json:"home"`
		Away *int `json:"away"`
	} `json:"fullTime"`
}

type MatchesResponse struct {
	Matches []Match `json:"matches"`
}

func main() {
	godotenv.Load(".env")
	matches, err := getMatches()
	if err != nil {
		log.Fatal(err)
	}
	now := time.Now()
	next, found := nextMatch(matches, now)
	if found {
		alertsDue(next, now)
	} else {
		log.Println("No upcoming matches found.")
	}
}

func getMatches() ([]Match, error) {
	apiKey := os.Getenv("FOOTBALL_DATA_API_KEY")
	if apiKey == "" {
		return nil, fmt.Errorf("FOOTBALL_DATA_API_KEY is not set in .env file")
	}
	req, err := http.NewRequest("GET", "https://api.football-data.org/v4/teams/86/matches", nil)
	if err != nil {
		return nil, err
	}

	req.Header.Set("X-Auth-Token", apiKey)
	client := &http.Client{
		Timeout: 5 * time.Second,
	}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("unexpected status: %d %s", resp.StatusCode, http.StatusText(resp.StatusCode))
	}
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	var response MatchesResponse

	err = json.Unmarshal(body, &response)
	if err != nil {
		return nil, err
	}
	return response.Matches, nil
}

func nextMatch(matches []Match, now time.Time) (Match, bool) {
	// Sort matches by date ascending
	sortedMatches := sortMatchesByDate(matches, true)
	for _, match := range sortedMatches {
		if match.UTCDate.After(now) && (match.Status != "POSTPONED" && match.Status != "CANCELLED") {
			return match, true
		}
	}
	return Match{}, false
}

func filterByStatus(matches []Match, status string) []Match {
	var filteredMatches []Match
	if status != "" {
		for _, match := range matches {
			if match.Status == status {
				filteredMatches = append(filteredMatches, match)
			}
		}
	} else {
		filteredMatches = slices.Clone(matches)
	}
	return filteredMatches
}

func sortMatchesByDate(matches []Match, ascending bool) []Match {
	sortedMatches := slices.Clone(matches)
	sort.Slice(sortedMatches, func(i, j int) bool {
		if ascending {
			return sortedMatches[i].UTCDate.Before(sortedMatches[j].UTCDate)
		}
		return sortedMatches[i].UTCDate.After(sortedMatches[j].UTCDate)
	})
	return sortedMatches
}

func formatMatch(match Match) string {
	var formatted string
	formatted += fmt.Sprintf("Date: %s, ", formatDate(match.UTCDate))
	formatted += fmt.Sprintf("Status: %s, ", match.Status)
	formatted += fmt.Sprintf("Home Team: %s, ", match.HomeTeam.Name)
	formatted += fmt.Sprintf("Away Team: %s, ", match.AwayTeam.Name)
	formatted += fmt.Sprintf("Competition: %s", match.Competition.Name)
	if match.Score.Winner != nil {
		formatted += fmt.Sprintf(", Winner: %s", formatWinner(match))
	}
	if match.Score.FullTime.Home != nil && match.Score.FullTime.Away != nil {
		formatted += fmt.Sprintf(", Full Time: %d - %d", *match.Score.FullTime.Home, *match.Score.FullTime.Away)
	}
	return formatted
}

func formatWinner(match Match) string {
	// Winner can be "HOME_TEAM", "AWAY_TEAM", or "DRAW", so it is HOME_TEAM return the home team name, if it is AWAY_TEAM return the away team name, if it is DRAW return "Draw"
	switch *match.Score.Winner {
	case "HOME_TEAM":
		return match.HomeTeam.Name
	case "AWAY_TEAM":
		return match.AwayTeam.Name
	case "DRAW":
		return "Draw"
	default:
		return "N/A"
	}
}

func formatDate(date time.Time) string {
	// Example: Wed, 14 Oct 2026 21:00 CST
	return date.In(mexicoCity).Format("Mon, 02 Jan 2006 15:04 MST")
}

func alertsDue(match Match, now time.Time) {
	// Check if the match is within 24 hours and not already sent
	if match.UTCDate.After(now) && match.UTCDate.Before(now.Add(24*time.Hour)) {
		sent, err := loadSentAlerts("sent_alerts.json")
		if err != nil {
			log.Fatal(err)
		}
		key := alertKey(match, "next")
		if !sent[key] {
			err := alertNextMatch(match)
			if err != nil {
				log.Fatal(err)
			}
			sent[key] = true
			err = saveSentAlerts("sent_alerts.json", sent)
			if err != nil {
				log.Fatal(err)
			}
		}
	}
}

func saveSentAlerts(path string, sent map[string]bool) error {
	// Save the sent alerts to a file
	alertData, err := json.Marshal(sent)
	if err != nil {
		return err
	}
	err = os.WriteFile(path, alertData, 0644)
	if err != nil {
		return err
	}
	return nil
}

func alertKey(match Match, kind string) string {
	// Create a unique key for the alert based on match ID and kind
	return fmt.Sprintf("%s_%d", kind, match.ID)
}

func loadSentAlerts(path string) (map[string]bool, error) {
	// Load the sent alerts from a file
	sentAlerts := make(map[string]bool)
	if _, err := os.Stat(path); os.IsNotExist(err) {
		return sentAlerts, nil
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	if len(data) == 0 {
		return sentAlerts, nil
	}
	err = json.Unmarshal(data, &sentAlerts)
	if err != nil {
		return nil, err
	}
	return sentAlerts, nil
}

func alertNextMatch(match Match) error {
	// NTFY_TOPIC_FOOTBALL via ntfy.sh
	topic := os.Getenv("NTFY_TOPIC_FOOTBALL")
	if topic == "" {
		return fmt.Errorf("NTFY_TOPIC_FOOTBALL is not set in .env file")
	}
	url := fmt.Sprintf("https://ntfy.sh/%s", topic)
	message := formatMatch(match)
	req, err := http.NewRequest("POST", url, strings.NewReader(message))
	if err != nil {
		return err
	}
	req.Header.Set("Title", "Next Match Alert")
	client := &http.Client{
		Timeout: 5 * time.Second,
	}
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		log.Printf("Unexpected status: %d %s\n", resp.StatusCode, http.StatusText(resp.StatusCode))
		return fmt.Errorf("unexpected status: %d %s", resp.StatusCode, http.StatusText(resp.StatusCode))
	}
	return nil
}
