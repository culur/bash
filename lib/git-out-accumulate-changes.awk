BEGIN { FS="\t" }
NF >= 2 {
    status = substr($1, 1, 1)
    file = $2
    
    if (!(file in first_status)) {
        first_status[file] = status
    }
    last_status[file] = status
}
END {
    for (file in first_status) {
        fs = first_status[file]
        ls = last_status[file]
        
        final_stat = ""
        if (fs == "A") {
            if (ls == "D") {
                final_stat = "AD"
            } else {
                final_stat = "A"
            }
        } else if (fs == "D") {
            if (ls == "A" || ls == "M" || ls == "T") {
                final_stat = "M"
            } else {
                final_stat = "D"
            }
        } else {
            if (ls == "D") {
                final_stat = "D"
            } else if (ls == "T") {
                final_stat = "T"
            } else {
                final_stat = "M"
            }
        }
        
        printf "[%s] %s\n", final_stat, file
    }
}
